from PIL import Image
import numpy as np
from scipy.ndimage.measurements import label
from scipy.ndimage.morphology import distance_transform_edt
from scipy.spatial import cKDTree
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
	prad = int(nozzle_diameter / 2 / resolution[1] + 0.5)
	def find_max_point(data):
		return np.unravel_index(np.argmax(data, axis=None), data.shape)
	def trace_from(start):
		def erase(a, b):
			step = 1/(prad*2)
			for t in xrange(prad*2):
				pos = (b[0]-a[0])*t*step+a[0], (b[1]-a[1])*t*step+a[1]
				feature[
					max(0, pos[0]-prad):min(feature.shape[0], pos[0]+prad),
					max(0, pos[1]-prad):min(feature.shape[1], pos[1]+prad)
				] = 0
		if feature[start] == 0:
			return
		head.moveTo(start)
		while True:
			corner = max(0, int(start[0]-prad*2)), max(0, int(start[1]-prad*2))
			idx = find_max_point(feature[
				corner[0]:corner[0]+prad*4,
				corner[1]:corner[1]+prad*4
			])
			idx = idx[0]+corner[0], idx[1]+corner[1]
			if feature[idx] == 0:
				break
			erase(start, idx)
			head.extrudeTo(idx)
			start = idx
	features = split_features(shell)
	for feature in features:
		while True:
			trace_from(find_max_point(feature))
			if np.count_nonzero(feature) == 0:
				break

class PrintHead(object):
	def __init__(self):
		self.pos = [0, 0, 0]
		self.layer = None
		self.layers = []

	def gcode(self):
		preamble = '''
M73 P0 ; enable build progress
G162 X Y F3000 ; home XY maximum
G161 Z F1200 ; home Z minimum
G92 Z-5 ; set Z to -5
G1 Z0 ; move Z to 0
G161 Z F100 ; home Z slowly
M132 X Y Z A B ; recall home offsets
G1 X-145 Y-75 Z30 F9000 ; move to wait position off table
G130 X20 Y20 Z20 A20 B20 ; lower stepper Vrefs while heating
M126 S100
M104 S235 T0
M133 T0 ; stabilize extruder temperature
G130 X127 Y127 Z40 A127 B127 ; default stepper Vrefs
G92 A0 ; zero extruder
G1 Z0.4 ; position nozzle
G1 E25 F300 ; purge nozzle
;G1 X-140 Y-70 Z0.15 F1200 ; slow wipe
G1 X-135 Y-65 Z0.5 F1200 ; lift
G92 A0 ; zero extruder
M73 P1 ;@body (notify GPX body has started)
G21
G90
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
		if self.layer is not None and len(self.layer) == 0:
			return
		self.layers.append([])
		self.layer = self.layers[-1]
		self.linear(z=len(self.layers) * resolution[0])

	def moveTo(self, (x, y)):
		x, y = x * resolution[1], y * resolution[2]
		self.linear(extrude=-1, x=x, y=y, feedrate=12000)

	def extrudeTo(self, (x, y)):
		x, y = x * resolution[1], y * resolution[2]
		filament = math.sqrt((self.pos[0]-x) ** 2 + (self.pos[1]-y) ** 2)
		self.linear(x=x, y=y, extrude=filament, feedrate=6000)

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
	print >>sys.stderr, '%i/%i' % (layer, cutdown.shape[0])
	head.addLayer()
	for shell in shells:
		print_shell(head, layer, shell[layer])
print >>sys.stderr, 'Outputting GCode'
print head.gcode()