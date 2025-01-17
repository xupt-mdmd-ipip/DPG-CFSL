import torch.nn.functional as F
from torch.autograd import Variable
from torch.utils.data import DataLoader, Dataset
import math
import argparse
import pickle

from sklearn import metrics

from sklearn.neighbors import KNeighborsClassifier
from matplotlib import pyplot
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import time
import utils
import imp
# from model.IDE_block import DPGN
# import model.CSA_block
from model.CSA_block import *
# import model.CSA_block
# import scipy.io as io
import os

##############2024/4/4#################
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

parser = argparse.ArgumentParser(description="Few Shot Visual Recognition")
parser.add_argument('--config', type=str, default=os.path.join(
    r'D:\pythoncode\test-IEEE_TNNLS_Gia-CFSL-main\IEEE_TNNLS_Gia-CFSL-main\config', 'paviaU.py'),
                    help='config file with parameters of the experiment. '
                         'It is assumed that the config file is placed under the directory ./config')
args = parser.parse_args()

# Hyper Parameters
config = imp.load_source("", args.config).config
train_opt = config['train_config']
data_path = config['data_path']
save_path = config['save_path']
source_data = config['source_data']
target_data = config['target_data']
target_data_gt = config['target_data_gt']

patch_size = train_opt['patch_size']
emb_size = train_opt['d_emb']
SRC_INPUT_DIMENSION = train_opt['src_input_dim']
TAR_INPUT_DIMENSION = train_opt['tar_input_dim']
N_DIMENSION = train_opt['n_dim']
CLASS_NUM = train_opt['class_num']
SHOT_NUM_PER_CLASS = train_opt['shot_num_per_class']
QUERY_NUM_PER_CLASS = train_opt['query_num_per_class']
EPISODE = train_opt['episode']
LEARNING_RATE = train_opt['lr']
lambda_1 = train_opt['lambda_1']
lambda_2 = train_opt['lambda_2']
GPU = config['gpu']
TEST_CLASS_NUM = train_opt['test_class_num']  # the number of class
TEST_LSAMPLE_NUM_PER_CLASS = train_opt['test_lsample_num_per_class']  # the number of labeled samples per class

utils.same_seeds(0)
# test_data = os.path.join(data_path, target_data)
# test_label = os.path.join(data_path, target_data_gt)
# Data_Band_Scaler, GroundTruth = utils.load_data(test_data, test_label)


# get train_loader and test_loader
def get_train_test_loader(Data_Band_Scaler, GroundTruth, class_num, shot_num_per_class, HalfWidth):
    # print(Data_Band_Scaler.shape)  # (610, 340, 103)
    [nRow, nColumn, nBand] = Data_Band_Scaler.shape

    '''label start'''
    num_class = int(np.max(GroundTruth))
    data_band_scaler = utils.flip(Data_Band_Scaler)
    groundtruth = utils.flip(GroundTruth)
    del Data_Band_Scaler
    del GroundTruth

    # HalfWidth
    G = groundtruth[nRow - HalfWidth:2 * nRow + HalfWidth, nColumn - HalfWidth:2 * nColumn + HalfWidth]
    data = data_band_scaler[nRow - HalfWidth:2 * nRow + HalfWidth, nColumn - HalfWidth:2 * nColumn + HalfWidth, :]

    [Row, Column] = np.nonzero(G)
    # print(Row)
    del data_band_scaler
    del groundtruth

    nSample = np.size(Row)
    print('number of sample', nSample)

    # Sampling samples
    train = {}
    test = {}
    da_train = {}  # Data Augmentation
    m = int(np.max(G))
    nlabeled = TEST_LSAMPLE_NUM_PER_CLASS
    print('labeled number per class:', nlabeled)
    # print((200 - nlabeled) / nlabeled + 1)
    # print(math.ceil((200 - nlabeled) / nlabeled) + 1)

    for i in range(m):
        indices = [j for j, x in enumerate(Row.ravel().tolist()) if G[Row[j], Column[j]] == i + 1]
        np.random.shuffle(indices)
        nb_val = shot_num_per_class
        train[i] = indices[:nb_val]
        da_train[i] = []
        for j in range(math.ceil((200 - nlabeled) / nlabeled) + 1):
            da_train[i] += indices[:nb_val]
        test[i] = indices[nb_val:]

    train_indices = []
    test_indices = []
    da_train_indices = []
    for i in range(m):
        train_indices += train[i]
        test_indices += test[i]
        da_train_indices += da_train[i]
    np.random.shuffle(test_indices)

    print('the number of train_indices:', len(train_indices))  # 520
    print('the number of test_indices:', len(test_indices))  # 9729
    # print('the number of train_indices after data argumentation:', len(da_train_indices))  # 520
    # print('labeled sample indices:', train_indices)

    nTrain = len(train_indices)
    nTest = len(test_indices)
    da_nTrain = len(da_train_indices)

    imdb = {}
    imdb['data'] = np.zeros([2 * HalfWidth + 1, 2 * HalfWidth + 1, nBand, nTrain + nTest],
                            dtype=np.float32)  # (9,9,100,n)
    imdb['Labels'] = np.zeros([nTrain + nTest], dtype=np.int64)
    imdb['set'] = np.zeros([nTrain + nTest], dtype=np.int64)

    RandPerm = train_indices + test_indices

    RandPerm = np.array(RandPerm)

    for iSample in range(nTrain + nTest):
        imdb['data'][:, :, :, iSample] = data[
                                         Row[RandPerm[iSample]] - HalfWidth:  Row[RandPerm[iSample]] + HalfWidth + 1,
                                         Column[RandPerm[iSample]] - HalfWidth: Column[
                                                                                    RandPerm[iSample]] + HalfWidth + 1,
                                         :]
        imdb['Labels'][iSample] = G[Row[RandPerm[iSample]], Column[RandPerm[iSample]]].astype(np.int64)

    imdb['Labels'] = imdb['Labels'] - 1  # 1-16 0-15
    imdb['set'] = np.hstack((np.ones([nTrain]), 3 * np.ones([nTest]))).astype(np.int64)
    # print('Data is OK.')

    train_dataset = utils.matcifar(imdb, train=True, d=3, medicinal=0)
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=class_num * shot_num_per_class, shuffle=False,
                                               num_workers=0)
    del train_dataset

    test_dataset = utils.matcifar(imdb, train=False, d=3, medicinal=0)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=100, shuffle=False, num_workers=0)
    del test_dataset
    del imdb

    # Data Augmentation for target domain for training
    imdb_da_train = {}
    imdb_da_train['data'] = np.zeros([2 * HalfWidth + 1, 2 * HalfWidth + 1, nBand, da_nTrain],
                                     dtype=np.float32)  # (9,9,100,n)
    imdb_da_train['Labels'] = np.zeros([da_nTrain], dtype=np.int64)
    imdb_da_train['set'] = np.zeros([da_nTrain], dtype=np.int64)

    da_RandPerm = np.array(da_train_indices)
    for iSample in range(da_nTrain):  # radiation_noise，flip_augmentation
        imdb_da_train['data'][:, :, :, iSample] = utils.radiation_noise(
            data[Row[da_RandPerm[iSample]] - HalfWidth:  Row[da_RandPerm[iSample]] + HalfWidth + 1,
            Column[da_RandPerm[iSample]] - HalfWidth: Column[da_RandPerm[iSample]] + HalfWidth + 1, :])
        imdb_da_train['Labels'][iSample] = G[Row[da_RandPerm[iSample]], Column[da_RandPerm[iSample]]].astype(np.int64)

    imdb_da_train['Labels'] = imdb_da_train['Labels'] - 1  # 1-16 0-15
    imdb_da_train['set'] = np.ones([da_nTrain]).astype(np.int64)
    # print('ok')

    return train_loader, test_loader, imdb_da_train, G, RandPerm, Row, Column, nTrain


def get_target_dataset(Data_Band_Scaler, GroundTruth, class_num, shot_num_per_class, patch_size):
    train_loader, test_loader, imdb_da_train, G, RandPerm, Row, Column, nTrain = get_train_test_loader(
        Data_Band_Scaler=Data_Band_Scaler, GroundTruth=GroundTruth,
        class_num=class_num, shot_num_per_class=shot_num_per_class, HalfWidth=patch_size // 2)
    train_datas, train_labels = next(train_loader.__iter__())
    # print('train labels:', train_labels)
    # print('size of train datas:', train_datas.shape)

    # print(imdb_da_train.keys())
    # print(imdb_da_train['data'].shape)
    # print(imdb_da_train['Labels'])
    del Data_Band_Scaler, GroundTruth

    # target data with data augmentation
    target_da_datas = np.transpose(imdb_da_train['data'], (3, 2, 0, 1))
    # print(target_da_datas.shape)
    target_da_labels = imdb_da_train['Labels']
    # print('target data augmentation label:', target_da_labels)

    # metatrain data for few-shot classification
    target_da_train_set = {}
    for class_, path in zip(target_da_labels, target_da_datas):
        if class_ not in target_da_train_set:
            target_da_train_set[class_] = []
        target_da_train_set[class_].append(path)
    target_da_metatrain_data = target_da_train_set
    # print(target_da_metatrain_data.keys())

    return train_loader, test_loader, target_da_metatrain_data, G, RandPerm, Row, Column, nTrain


# model
def conv3x3x3(in_channel, out_channel):
    layer = nn.Sequential(
        nn.Conv3d(in_channels=in_channel, out_channels=out_channel, kernel_size=3, stride=1, padding=1, bias=False),
        nn.BatchNorm3d(out_channel),
        # nn.ReLU(inplace=True)
    )
    return layer


def conv3x3x3_ft(in_channel, out_channel):
    layer = nn.Sequential(
        nn.Conv3d(in_channels=in_channel, out_channels=out_channel, kernel_size=3, stride=1, padding=1, bias=False),
        FeatureWiseTransformation2d_fw(out_channel),
        # nn.ReLU(inplace=True)
    )
    return layer


class residual_block(nn.Module):

    def __init__(self, in_channel, out_channel):
        super(residual_block, self).__init__()

        self.conv1 = conv3x3x3(in_channel, out_channel)
        self.conv2 = conv3x3x3(out_channel, out_channel)
        self.conv3 = conv3x3x3(out_channel, out_channel)

    def forward(self, x):  # (1,1,100,9,9)
        x1 = F.relu(self.conv1(x), inplace=True)  # (1,8,100,9,9)  (1,16,25,5,5)
        x2 = F.relu(self.conv2(x1), inplace=True)  # (1,8,100,9,9) (1,16,25,5,5)
        x3 = self.conv3(x2)  # (1,8,100,9,9) (1,16,25,5,5)

        out = F.relu(x1 + x3, inplace=True)  # (1,8,100,9,9)  (1,16,25,5,5)
        return out


# --- feature-wise transformation layer ---
def softplus(x):
    return torch.nn.functional.softplus(x, beta=100)


class FeatureWiseTransformation2d_fw(nn.BatchNorm2d):
    feature_augment = True

    def __init__(self, num_features, momentum=0.1, track_running_stats=True):
        super(FeatureWiseTransformation2d_fw, self).__init__(num_features, momentum=momentum,
                                                             track_running_stats=track_running_stats)
        self.weight.fast = None
        self.bias.fast = None
        if self.track_running_stats:
            self.register_buffer('running_mean', torch.zeros(num_features))
            self.register_buffer('running_var', torch.zeros(num_features))
        if self.feature_augment:  # initialize {gamma, beta} with {0.3, 0.5}
            self.gamma = torch.nn.Parameter(torch.ones(1, num_features, 1, 1, 1) * 0.3)
            self.beta = torch.nn.Parameter(torch.ones(1, num_features, 1, 1, 1) * 0.5)
        self.reset_parameters()

    def reset_running_stats(self):
        if self.track_running_stats:
            self.running_mean.zero_()
            self.running_var.fill_(1)

    def forward(self, x, step=0):
        if self.weight.fast is not None and self.bias.fast is not None:
            weight = self.weight.fast
            bias = self.bias.fast
        else:
            weight = self.weight
            bias = self.bias
        if self.track_running_stats:
            out = F.batch_norm(x, self.running_mean, self.running_var, weight, bias, training=self.training,
                               momentum=self.momentum)
        else:
            out = F.batch_norm(x, torch.zeros_like(x), torch.ones_like(x), weight, bias, training=True, momentum=1)

        # apply feature-wise transformation
        if self.feature_augment and self.training:
            gamma = (1 + torch.randn(1, self.num_features, 1, 1, 1, dtype=self.gamma.dtype,
                                     device=self.gamma.device) * softplus(self.gamma)).expand_as(out)
            beta = (torch.randn(1, self.num_features, 1, 1, 1, dtype=self.beta.dtype,
                                device=self.beta.device) * softplus(self.beta)).expand_as(out)
            out = gamma * out + beta
        return out


class D_Res_3d_CNN(nn.Module):
    def __init__(self, in_channel, out_channel1, out_channel2, patch_size, emb_size):
        super(D_Res_3d_CNN, self).__init__()
        self.in_channel = in_channel
        self.emb_size = emb_size
        self.patch_size = patch_size
        self.block1 = residual_block(in_channel, out_channel1)
        self.maxpool1 = nn.MaxPool3d(kernel_size=(4, 2, 2), padding=(0, 1, 1), stride=(4, 2, 2))
        self.block2 = residual_block(out_channel1, out_channel2)
        self.maxpool2 = nn.MaxPool3d(kernel_size=(4, 2, 2), stride=(4, 2, 2), padding=(2, 1, 1))
        self.conv = nn.Conv3d(in_channels=out_channel2, out_channels=32, kernel_size=3, bias=False)

        self.layer_second = nn.Sequential(nn.Linear(in_features=self._get_layer_size()[0],
                                                    out_features=self.emb_size,
                                                    bias=True),
                                          nn.BatchNorm1d(self.emb_size))

        self.layer_last = nn.Sequential(nn.Linear(in_features=self._get_layer_size()[1],
                                                  out_features=self.emb_size,
                                                  bias=True),
                                        nn.BatchNorm1d(self.emb_size))

    def _get_layer_size(self):
        with torch.no_grad():
            x = torch.zeros((1, 1, 100,
                             self.patch_size, self.patch_size))
            x = self.block1(x)
            x = self.maxpool1(x)
            x = self.block2(x)
            x = self.maxpool2(x)
            _, t, c, w, h = x.size()
            s1 = t * c * w * h
            x = self.conv(x)
            x = x.view(x.shape[0], -1)
            s2 = x.size()[1]
        return s1, s2

    def forward(self, x):
        x = x.unsqueeze(1)
        x = self.block1(x)
        x = self.maxpool1(x)
        x = self.block2(x)
        x = self.maxpool2(x)
        inter = x
        inter = inter.view(inter.shape[0], -1)
        inter = self.layer_second(inter)
        x = self.conv(x)
        x = x.view(x.shape[0], -1)
        x = self.layer_last(x)
        out = []
        out.append(inter)
        out.append(x)
        return out


class Mapping(nn.Module):
    def __init__(self, in_dimension, out_dimension):
        super(Mapping, self).__init__()
        self.preconv = nn.Conv2d(in_dimension, out_dimension, 1, 1, bias=False)
        self.preconv_bn = nn.BatchNorm2d(out_dimension)

    def forward(self, x):
        x = self.preconv(x)
        x = self.preconv_bn(x)
        return x

"""
定义了一个包含特征编码器和两个映射器的神经网络模型，根据传入的域参数选择不同的映射器进行操作，并将结果输入到特征编码器中得到特征表示。
"""
class Network(nn.Module):
    def __init__(self, patch_size, emb_size):
        super(Network, self).__init__()
        self.feature_encoder = D_Res_3d_CNN(1, 8, 16, patch_size, emb_size)
        self.target_mapping = Mapping(TAR_INPUT_DIMENSION, N_DIMENSION)
        self.source_mapping = Mapping(SRC_INPUT_DIMENSION, N_DIMENSION)

    def forward(self, x, domain='source'):
        if domain == 'target':
            x = self.target_mapping(x)
        elif domain == 'source':
            x = self.source_mapping(x)
        feature = self.feature_encoder(x)
        return feature

def main(imgPath,savePath):
    #test_data = os.path.join(data_path, target_data)
    #imgPath=test_data
    print('imaPath',imgPath)
    test_label = os.path.join(data_path, target_data_gt)
    print('test_label',test_label)
    Data_Band_Scaler, GroundTruth = utils.load_data(imgPath, test_label)

    train_loader, test_loader, _, G, RandPerm, Row, Column, nTrain = get_target_dataset(
        Data_Band_Scaler=Data_Band_Scaler, GroundTruth=GroundTruth, class_num=TEST_CLASS_NUM,
        shot_num_per_class=TEST_LSAMPLE_NUM_PER_CLASS, patch_size=patch_size)
    feature_encoder = Network(patch_size, emb_size)
    feature_encoder.to(GPU)


    num = 5
    pkl_addr = r"D:\pythoncode\test-IEEE_TNNLS_Gia-CFSL-main\IEEE_TNNLS_Gia-CFSL-main/results/{}/feature_encoder_best_loss.pth".format(num)
    state_dict = torch.load(pkl_addr, map_location='cuda:0')
    feature_encoder.load_state_dict(state_dict)

    print("Testing ...")
    train_end = time.time()
    feature_encoder.eval()
    total_rewards = 0
    counter = 0
    predict = np.array([], dtype=np.int64)
    labels = np.array([], dtype=np.int64)
    train_datas, train_labels = next(train_loader.__iter__())
    _, train_features = feature_encoder(Variable(train_datas).to(GPU), domain='target')
    max_value = train_features.max()
    min_value = train_features.min()
    train_features = (train_features - min_value) * 1.0 / (max_value - min_value)

    KNN_classifier = KNeighborsClassifier(n_neighbors=1)
    KNN_classifier.fit(train_features.cpu().detach().numpy(), train_labels)
    test_labels_all, feature_emb = [], []
    for test_datas, test_labels in test_loader:
        batch_size = test_labels.shape[0]

        _, test_features = feature_encoder(Variable(test_datas).to(GPU), domain='target')
        feature_emb.append(test_features.cpu().detach().numpy())
        test_features = (test_features - min_value) * 1.0 / (max_value - min_value)
        predict_labels = KNN_classifier.predict(test_features.cpu().detach().numpy())
        print('predict_labels.shape',predict_labels.shape)

        test_labels = test_labels.numpy()
        test_labels_all.append(test_labels)
        rewards = [1 if predict_labels[j] == test_labels[j] else 0 for j in range(batch_size)]

        total_rewards += np.sum(rewards)
        counter += batch_size

        predict = np.append(predict, predict_labels)
        labels = np.append(labels, test_labels)

        accuracy = total_rewards / 1.0 / counter
    test_accuracy = 100. * total_rewards / len(test_loader.dataset)
    test_end = time.time()
    oa = round(test_accuracy, 2)
    C = metrics.confusion_matrix(labels, predict)
    ca = np.diag(C) / np.sum(C, 1, dtype=float)
    aa = np.mean(ca)
    best_G, best_RandPerm, best_Row, best_Column, best_nTrain = G, RandPerm, Row, Column, nTrain
    kappa = metrics.cohen_kappa_score(labels, predict)
    print("OA: " + "{:.2f}".format(oa))
    print("AA: " + "{:.2f}".format(100 * aa))
    print("kappa: " + "{:.2f}".format(100 * kappa))
    print("accuracy for each class: ", np.around(100 * ca, 2))
    best_predict_all = predict
    for i in range(len(best_predict_all)):
        best_G[best_Row[best_RandPerm[best_nTrain + i]]][best_Column[best_RandPerm[best_nTrain + i]]] = \
            best_predict_all[i] + 1
    utils.my_classification_map(best_G[4:-4, 4:-4], oa=oa, dpi=24, data_name='PaviaU', method='Gia', address=savePath)
    print("test time per DataSet(s): " + "{:.5f}".format(test_end - train_end))

if __name__ == '__main__':
    main('./item/uploads/PaviaU.mat','./item/static/predictImage.png')