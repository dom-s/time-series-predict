"""
prepare features for classifier
"""

import os
import re
import numpy as np
from parse_stock_files import *

class FeatureExtractor:
    """
    extract feature from raw data
    """
    def __init__(self, path_lda, path_stocks, path_corpus, path_features):
        self.path_lda = path_lda # path to lda results
        self.path_stocks = path_stocks # path to stock data
        self.path_corpus = path_corpus # path to NYT corpus
        self.path_features = path_features # path to feature-file (libsvm style)
        self.topic_distribution = []

        try:
            os.stat(self.path_lda+"final.topic")
        except:
            self.get_topic_distribution()

        try:
            os.stat(self.path_corpus+"corpus_stock.csv")
        except:
            self.merge_corpus()

        try:
            os.stat(self.path_corpus+"corpus_label.csv")
        except:
            self.generate_label()

        # self.features_topic_dist()

    def get_topic_distribution(self, fname="final.topic"):
        print "generating topic distribution with lda results ...",
        # get alpha
        alpha = 0.
        with open(self.path_lda+"final.other", "r") as f:
            lines = f.readlines()
            for line in lines:
                if "alpha" in line:
                    alpha = float(line.strip().split()[-1])
                    print "alpha:", alpha,
                    break

        with open(self.path_lda+"final.gamma", "r") as f:
            lines = f.readlines()
        fout = open(self.path_lda + fname, "w")

        for line in lines:
            probs = line.strip().split()
            probs = [float(prob)-alpha for prob in probs]
            probs_sum = sum(probs)
            probs = [str(prob/probs_sum) for prob in probs]
            s = " ".join(probs)
            fout.write(s + "\n")
        fout.close()
        print "done!"

    def merge_corpus(self, fout_name="corpus_stock.csv"):
        """
        merge stock data and news corpus
        write to "~/lda/corpus_stock.csv"
        each line: {company name} {date} {document index} {stock price}
        """
        print "merge stock data with news corpus ...",
        # load stock price from raw files
        path_raw = "stocks-raw/"
        cs_dict = company_stock_dictionary(self.path_stocks + "company-stock-mapping.csv")
        stock_data = dict() # (company, date) -> stock

        def load_stock(file_name):
            company = re.sub(r'.*_', '', file_name)
            company = company.replace('.csv', '')
            company = cs_dict[company]
            with open(self.path_stocks+path_raw+file_name, "r") as f:
                lines = f.readlines()
            for line in lines[1:]:
                line = line.strip().split(",")
                date = line[0]
                price = line[4]
                stock_data[(company, date)] = price

        files_raw = os.listdir(self.path_stocks+path_raw)
        for file_raw in files_raw:
            load_stock(file_raw)

        # merge with news corpus
        with open(self.path_corpus+"corpus_raw.txt", "r") as f:
            lines = f.readlines()

        fout = open(self.path_corpus+fout_name, "w")
        cnt = 0
        for i in xrange(len(lines)):
            line = lines[i].strip().split("\t")
            date = re.sub(r'T.*?Z', '', line[1])
            if (line[0], date) in stock_data:
                s = line[0] + "," + date + "," + str(i) + "," + stock_data[(line[0], date)]
                fout.write(s+"\n")
                cnt += 1
        fout.close()
        print "done!", cnt, "records merged!"

    def generate_label(self, f_stock="corpus_stock.csv", f_label="corpus_label.csv"):
        print "generating labels ...",

        with open(self.path_corpus+f_stock, "r") as f:
            lines = f.readlines()
        fout = open(self.path_corpus+f_label, "w")
        cnt_pos = 0
        cnt_neg = 1

        for i in xrange(len(lines)-1):
            line = lines[i].strip().split(",")
            line_next = lines[i+1].strip().split(",")
            if line[0] == line_next[0]:
                change = float(line_next[-1])/float(line[-1]) - 1.
                label = significant_change(change*100.)
            else:
                label = 0
            if label == 1:
                cnt_pos += 1
            else:
                cnt_neg += 1
            fout.write(lines[i].strip()+","+str(label)+"\n")
        fout.write(lines[-1].strip()+",0\n")
        fout.close()
        print "done!", cnt_pos, "positives and", cnt_neg, "negatives"

    def features_topic_dist(self,
                            f_lda_topic="final.topic",
                            f_corpus="corpus_label.csv",
                            fileout="topic_dist.csv"):
        with open(self.path_lda+f_lda_topic, "r") as f:
            self.topic_distribution = f.readlines()
        with open(self.path_corpus+f_corpus, "r") as f:
            lines = f.readlines()
        fout = open(self.path_features+fileout, "w")

        for line in lines:
            line = line.strip().split(",")
            s = line[-1] + " "
            features = self.topic_distribution[int(line[2])]
            features = features.strip().split()
            for i in xrange(len(features)):
                s += str(i+1) + ":" + str(features[i]) + " "
            fout.write(s+"\n")
        fout.close()


class FeatureGenerator:
    """
    generate new feature from current feature files
    """
    def __init__(self,
                 path_features,
                 path_lda="../results/lda/",
                 f_corpus=None,
                 f_sentiment=None,
                 decay=0.75, window_size=1):
        self.path_features = path_features
        self.path_lda = path_lda
        self.decay = decay
        self.window_size = window_size

        self.index = []
        self.company = []
        self.labels = []
        self.topic_dist = []
        self.topic_hist = []

        self.sentiment = []
        self.index_sentiment = []

        self.load_corpus(f_corpus)
        if f_sentiment:
            self.load_sentiment(f_sentiment)

    def load_corpus(self, f_corpus):
        with open(f_corpus, "r") as f:
            corpus = f.readlines()

        self.index = []
        self.company = []
        self.labels = []

        for record in corpus:
            record = record.strip().split(",")
            self.index.append(int(record[2]))
            self.company.append(record[0])
            self.labels.append(int(record[-1]))

    def load_topic_dist(self, f_lda_topic):
        self.topic_dist = []
        with open(f_lda_topic, "r") as f:
            topic_distributions = f.readlines()

        for idx in self.index:
            topic_dist = topic_distributions[idx].strip().split()
            topic_dist = np.array([float(td) for td in topic_dist])
            self.topic_dist.append(topic_dist)

    def load_sentiment(self, f_sentiment):
        """
        load sentiment features
        """
        with open(f_sentiment, "r") as f:
            lines = f.readlines()
        self.sentiment = []
        self.index_sentiment = dict()

        for idx in range(len(lines)):
            record = lines[idx].strip().split(",")
            self.sentiment.append(list(record[-3:]))
            self.index_sentiment[int(record[2])] = idx

    def generate_topic_hist(self):
        for folder in os.listdir(self.path_lda):
            if "lda_result" not in folder:
                continue
            topic_num = folder.split("_")[-1]
            self.load_topic_dist(f_lda_topic=self.path_lda + folder + "/final.topic")
            self.feature_topic_hist()

            # concatenate
            features = []
            for idx in range(len(self.topic_hist)):
                features.append(list(self.topic_dist[idx]) + list(self.topic_hist[idx]))
            path_out = "{0}topic_hist_d{1}_w{2}_cont/".format(self.path_features, self.decay, self.window_size)
            try:
                os.stat(path_out)
            except:
                os.mkdir(path_out)
            file_out = "{0}topic_dist_{2}_hist_d{1}_w{3}_cont.txt".format(path_out, self.decay, topic_num, self.window_size)
            self.output_features(features=features, labels=self.labels, file_out=file_out)

            # add
            features = []
            for idx in range(len(self.topic_hist)):
                features.append(list(self.topic_dist[idx] + self.topic_hist[idx]))
            path_out = "{0}topic_hist_d{1}_w{2}/".format(self.path_features, self.decay, self.window_size)
            try:
                os.stat(path_out)
            except:
                os.mkdir(path_out)
            file_out = "{0}topic_dist_{2}_hist_d{1}_w{3}.txt".format(path_out, self.decay, topic_num, self.window_size)
            self.output_features(features=features, labels=self.labels, file_out=file_out)

    def add_sentiment(self, f_feature, file_out):
        # load features from exsiting file
        with open(self.path_features+f_feature, "r") as f:
            lines = f.readlines()
        fout = open(self.path_features+file_out, "w")

        for lidx in range(len(lines)):
            if self.index[lidx] not in self.index_sentiment:
                continue
            sentiment_idx = self.index_sentiment[self.index[lidx]]
            feature_num = len(lines[lidx].strip().split())
            s = lines[lidx].strip() + " "
            for i in range(3):
                s += str(i+feature_num) + ":" + self.sentiment[sentiment_idx][i] + " "
            fout.write(s + "\n")
        fout.close()

    def feature_topic_hist(self):
        self.topic_hist = []
        for idx in range(len(self.topic_dist)):
            topic_hist = np.zeros(self.topic_dist[idx].shape)
            for idx_w in range(1, self.window_size+1):
                if idx-idx_w < 0:
                    continue
                if self.company[idx-idx_w] != self.company[idx]: # out of boundry
                    continue
                topic_hist += self.topic_dist[idx-idx_w] * (self.decay ** idx_w)
            self.topic_hist.append(topic_hist)

    def output_features(self, features, labels, file_out):
        fout = open(file_out, "w")
        for i in range(len(features)):
            s = str(labels[i]) + " "
            feature = features[i]
            for idx in range(len(feature)):
                s += str(idx+1) + ":" + str(feature[idx]) + " "
            #print s
            fout.write(s + "\n")
        fout.close()


if __name__ == "__main__":

    '''
    path_lda = "../results/lda_result/"
    path_stocks = "../data/stocks/"
    path_corpus = "../data/lda/"
    path_features = "../data/features/"
    feature_extractor = FeatureExtractor(path_lda=path_lda,
                                         path_stocks=path_stocks,
                                         path_corpus=path_corpus,
                                         path_features=path_features)
    '''


    # ===========================================
    # extract topic distribution from raw data
    # structure data into libSVM format
    # ===========================================
    """
    path_lda = "../results/lda/"
    path_stocks = "../data/stocks/"
    path_corpus = "../data/lda/"
    path_features = "../data/features/"

    folders = os.listdir(path_lda)
    for folder in folders:
        k = folder.split("_")[-1]
        FE = FeatureExtractor(path_lda=path_lda+folder+"/",
                              path_stocks=path_stocks,
                              path_corpus=path_corpus,
                              path_features=path_features)
        FE.features_topic_dist(f_lda_topic="final.topic",
                               f_corpus="corpus_label.csv",
                               fileout="topic_dist_"+k+".csv")
    """


    # ===========================================
    # generate topic_hist
    # ===========================================
    '''
    path_lda = "../results/lda/"
    path_features = "../data/features/"
    f_corpus = "../data/lda/corpus_label.csv"
    params_decay = [0.9, 0.7]
    params_window_size = [1, 2]

    for decay in params_decay:
        for window_size in params_window_size:
            FG = FeatureGenerator(path_features=path_features, path_lda=path_lda, f_corpus=f_corpus,
                                  decay=decay, window_size=window_size)
            FG.generate_topic_hist()
    '''

    # ===========================================
    # add sentiment features
    # ===========================================
    '''
    path_features = "../data/features/"
    f_corpus = "../data/lda/corpus_label.csv"
    f_sentiment = "../data/sentiment.txt"

    FG = FeatureGenerator(path_features=path_features, f_corpus=f_corpus, f_sentiment=f_sentiment)
    folders = os.listdir(path_features)
    for folder in folders:
        if "hist" not in folder:
            continue
        new_folder = folder + "_sentiment"
        try:
            os.stat(path_features + new_folder)
        except:
            os.mkdir(path_features + new_folder)
        for feature_file in os.listdir(path_features+folder+"/"):
            FG.add_sentiment(f_feature=folder+"/"+feature_file,
                             file_out=new_folder+"/"+feature_file.replace(".txt", "_sentiment.txt"))
    '''
