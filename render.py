import sys, time, datetime
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GL.shaders import *
from OpenGL.arrays import vbo
from OpenGL.raw.GL.ARB.vertex_array_object import glGenVertexArrays, glBindVertexArray
from PIL import Image
import numpy
import json

vert = '''
attribute vec3 p;
void main() {
	gl_Position = p.xyzz;
}
'''

frag = '''
uniform float layer;
uniform vec3 resolution;
float distance_field(vec3 p) {
	return min(min(max(-(length(p / vec3(4., 4., 1.) - vec3(5.5, 5.5, 5.1)) - 4.), length(p / vec3(4., 4., 1.) - vec3(5.5, 5.5, 5.1)) - 4.8), length(p / vec3(4., 4., .5) - vec3(5.5, 5.5, 5.1)) - 3.), length(p / vec3(4., 4., .5) - vec3(2.5, 2.5, 2.1)) - 1.);
}
void main() {
	vec3 p = vec3(gl_FragCoord.xy, layer) * resolution;
	gl_FragColor = vec4(distance_field(p) <= 0. ? vec3(1.) : vec3(0.), 1.);
}
'''

width = 500
height = 500
layers = 100

x_res = .1 # mm
y_res = .1
z_res = .1

json.dump(((width, height, layers), (x_res, y_res, z_res)), file('layers/spec.json', 'w'))

cur_layer = 0

def init():
	global program, vertexPositions, indexPositions
	glClearColor(0, 1, 0, 0)

	program = compileProgram(
		compileShader(vert, GL_VERTEX_SHADER), 
		compileShader(frag, GL_FRAGMENT_SHADER)
	)
	vertices = numpy.array([[-1,-1,0],[1,-1,0],[1,1,0], [1,1,0],[-1,1,0],[-1,-1,0]], dtype='f')
	vertexPositions = vbo.VBO(vertices)
	indices = numpy.array([[0,1,2],[3,4,5]], dtype=numpy.int32)
	indexPositions = vbo.VBO(indices, target=GL_ELEMENT_ARRAY_BUFFER)
	glEnableVertexAttribArray(glGetAttribLocation(program, 'p'))

def render():
	global im, cur_layer
	glClear(GL_COLOR_BUFFER_BIT)
	glUseProgram(program)
	glViewport(0, 0, width, height)
	glUniform3f(glGetUniformLocation(program, 'resolution'), x_res, y_res, z_res)
	glUniform1f(glGetUniformLocation(program, 'layer'), cur_layer)
	print 'Layers left:', layers - cur_layer
	indexPositions.bind()
	vertexPositions.bind()
	glEnableVertexAttribArray(0)
	glVertexAttribPointer(0, 3, GL_FLOAT, False, 0, None)
	glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
	data = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE, outputType=None)
	data = numpy.flipud(data.reshape((height, width, 3)).astype(numpy.uint8))
	im = Image.fromarray(data)
	im.save('layers/layer_%i.png' % cur_layer)
	cur_layer += 1

	glutSwapBuffers()
	if cur_layer < layers:
		glutPostRedisplay()
	else:
		sys.exit(0)

glutInit([])
glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB)
glutInitWindowSize(width, height)
glutCreateWindow("AjaPrint Renderer")
glutDisplayFunc(render)

init()

glutMainLoop()