from PIL import Image
import numpy as np
from scipy.ndimage.measurements import label
from scipy.ndimage.morphology import distance_transform_edt
import scipy.misc
import json, math, sys
from matplotlib import pyplot as plt
nozzle_diameter = .4 # mm
outline_overlap = .1 # mm
num_shells = 2

def load():
	dimensions, resolution = json.load(file('layers/spec.json'))
	dimensions = dimensions[2], dimensions[0], dimensions[1]
	resolution = resolution[2], resolution[0], resolution[1]
	data = np.zeros(dimensions, np.int8)
	
	for i in xrange(dimensions[0]):
		im = Image.open('layers/layer_%i.png' % i)
		data[i] = np.array(im)[:,:,0] + 1

	return dimensions, resolution, data

def find_solid(data):
	data, features = label(data)
	return (data != data[0,0,0]).astype(np.int32)

def remove_borders(data):
	def shorten(dim, getter):
		for i in xrange(dimensions[dim]):
			if 1 not in getter(i):
				ranges[dim][0] += 1
			else:
				break
		for i in xrange(dimensions[dim], 0, -1):
			if 1 not in getter(i-1):
				ranges[dim][1] -= 1
			else:
				break
		if ranges[dim][0] > 0:
			ranges[dim][0] -= 1
		if ranges[dim][1] < dimensions[dim]:
			ranges[dim][1] += 1

	ranges = [[0, dimensions[0]], [0, dimensions[1]], [0, dimensions[2]]]
	shorten(0, lambda i: data[i])
	shorten(1, lambda i: data[:,i])
	shorten(2, lambda i: data[:,:,i])
	return data[ranges[0][0]:ranges[0][1], ranges[1][0]:ranges[1][1], ranges[2][0]:ranges[2][1]]

# Should this work in 3d?
def tag_distance(data):
	out = np.empty(data.shape)
	for i in xrange(data.shape[0]):
		out[i] = distance_transform_edt(data[i])
	return out

def find_shells(data):
	shells = []
	nozzle_pixels = nozzle_diameter / resolution[1]
	overlap = outline_overlap / resolution[1]
	cutdown = np.copy(data)
	for i in xrange(num_shells):
		shell = np.copy(cutdown)
		shell[shell > nozzle_pixels] = 0
		shells.append(shell)
		cutdown -= nozzle_pixels - overlap
		np.clip(cutdown, 0, np.inf, out=cutdown)
	return cutdown, shells

def split_features(data):
	fdata, features = label(data)
	out = []
	for i in xrange(1, features+1):
		isolated = np.copy(fdata)
		isolated[isolated != i] = 0
		out.append(distance_transform_edt(isolated))
	return out

def print_shell(head, layer, shell):
	features = split_features(shell)
	for i, feature in enumerate(features):
		pass

class PrintHead(object):
	def __init__(self):
		self.pos = [0, 0, 0]
		self.layer = None
		self.layers = []

	def gcode(self):
		preamble = '''
G21
G90
G1 F1500
'''
		return preamble.lstrip() + '\n'.join('\n'.join(layer) for layer in self.layers)

	def linear(self, x=None, y=None, z=None, extrude=None, feedrate=None):
		command = 'G1'
		if x is not None and x != self.pos[0]:
			command += ' X%f' % x
			self.pos[0] = x
		if y is not None and y != self.pos[1]:
			command += ' Y%f' % y
			self.pos[1] = y
		if z is not None and z != self.pos[2]:
			command += ' Z%f' % z
			self.pos[2] = z
		if extrude is not None:
			command += ' E%f' % extrude
		if feedrate is not None:
			command += ' F%f' % feedrate
		if command == 'G1':
			return
		self.layer.append(command)

	def addLayer(self):
		self.layers.append([])
		self.layer = self.layers[-1]
		self.linear(z=len(self.layers) * resolution[0])
		self.moveTo(10, 5)
		self.extrudeTo(30, 10)

	def moveTo(self, x, y):
		self.linear(x=x, y=y)

	def extrudeTo(self, x, y):
		filament = math.sqrt((self.pos[0]-x) ** 2 + (self.pos[1]-y) ** 2)
		self.linear(x=x, y=y, extrude=filament)

np.set_printoptions(threshold=np.nan)
print >>sys.stderr, 'Loading'
dimensions, resolution, data = load()
print >>sys.stderr, 'Finding solids'
data = find_solid(data)
print >>sys.stderr, 'Trimming fat'
data = remove_borders(data)
print >>sys.stderr, 'Tagging distance'
data = tag_distance(data)
print >>sys.stderr, 'Finding shells'
cutdown, shells = find_shells(data)
print >>sys.stderr, 'Printing layers'
head = PrintHead()
for layer in xrange(cutdown.shape[0]):
	head.addLayer()
	for shell in shells:
		print_shell(head, layer, shell[layer])
print >>sys.stderr, 'Outputting GCode'
print head.gcode()