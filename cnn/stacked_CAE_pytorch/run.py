import argparse
import os
import shutil
import time

import torch
import torchvision
from torch import nn
from torch.autograd import Variable
from torch.utils.data import DataLoader
from torchvision import transforms
from torchvision.datasets import MNIST, CIFAR10
from torchvision.utils import save_image

from model import StackedAutoEncoder
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

parser = argparse.ArgumentParser(description='PyTorch CAE Training')
parser.add_argument('--gpu', default=[0,1],
                    help='used gpu', type=str)
parser.add_argument('--save-dir', default='stackedCAE', dest='save_dir',
                    help='The directory used to save the trained models'
                    , type=str)
global args
args = parser.parse_args()

# Check the save_dir exists or not
save_result_path = 'results/' + args.save_dir
if not os.path.exists(save_result_path):
    os.makedirs(save_result_path)

if not os.path.exists(save_result_path + '/imgs'):
    os.mkdir(save_result_path + '/imgs')

num_epochs = 1000
batch_size = 128

def to_img(x):
    x = x.view(x.size(0), 3, 32, 32)
    return x

def main():
    img_transform = transforms.Compose([
        #transforms.RandomRotation(360),
        # transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0, hue=0),
        transforms.ToTensor(),
    ])

    dataset = CIFAR10(root='./data', transform=img_transform)
    # Data Loader for easy mini-batch return in training
    dataloader = DataLoader(dataset,
                    batch_size=batch_size,
                    shuffle=True,
                    num_workers=8)


    model = StackedAutoEncoder().cuda()
    os.environ["CUDA_VISIBLE_DEVICES"] = ','.join(str(x) for x in args.gpu)
    print('Running model on GPUs {}......'.format(','.join(str(x).split(',')[0] for x in args.gpu)))
    if torch.cuda.device_count() > 1:
      model = nn.DataParallel(model)

    model.to(device)

    start_time = time.time()
    for epoch in range(num_epochs):
        if epoch % 10 == 0:
            # Test the quality of our features with a randomly initialzed linear classifier.
            classifier = nn.Linear(512 * 16, 10).cuda() # in_features = 512*16, out_features = 10
            criterion = nn.CrossEntropyLoss()
            optimizer = torch.optim.Adam(classifier.parameters(), lr=0.001)

        model.train() # self.training = True
        total_time = time.time()
        correct = 0
        for i, data in enumerate(dataloader):
            img, target = data
            target = Variable(target).cuda()
            img = Variable(img).cuda()
            features = model(img).detach() # call StackedAutoEncoder's forward()
            prediction = classifier(features.view(features.size(0), -1))  # Set in_features as feature extracted; feed the features trained from CAE to a linear classifier
            loss = criterion(prediction, target)

            # Zero gradients, perform a backward pass, and update the weights.
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            pred = prediction.data.max(1, keepdim=True)[1]
            correct += pred.eq(target.data.view_as(pred)).cpu().sum()

        total_time = time.time() - total_time

        model.eval()
        img, _ = data
        img = Variable(img).cuda()
        features, x_reconstructed = model(img)
        reconstruction_loss = torch.mean((x_reconstructed.data - img.data)**2) # MSE

        if epoch % 10 == 0:
            print("Saving epoch {}".format(epoch))
            orig = to_img(img.cpu().data)
            save_image(orig, './' + save_result_path + '/imgs/orig_{}.png'.format(epoch))
            pic = to_img(x_reconstructed.cpu().data)
            save_image(pic, './' + save_result_path + '/imgs/reconstruction_{}.png'.format(epoch))

        print("Epoch {} complete\tTime: {:.4f}s\t\tLoss: {:.4f}".format(epoch, total_time, reconstruction_loss))
        print("Feature Statistics\tMean: {:.4f}\t\tMax: {:.4f}\t\tSparsity: {:.4f}%".format(
            torch.mean(features.data), torch.max(features.data), torch.sum(features.data == 0.0)*100 / features.data.numel())
        )
        print("Linear classifier performance: {}/{} = {:.2f}%".format(correct, len(dataloader)*batch_size, 100*float(correct) / (len(dataloader)*batch_size)))
        print("="*80)

    end_time = time.time() - start_time
    print("Total training time: {:.2f} sec".format(end_time))
    torch.save(model.state_dict(), './' + save_result_path + '/CDAE.pth')

if __name__ == '__main__':
    main()
