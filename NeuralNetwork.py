import cupy as cp
import numpy as np
from functools import reduce
from Engeneeringthesis.kernels import dot_cuda_paralell, max_pooling_cuda_paralell, convolve_cuda_paralell, dot_cuda_paralell_many_inputs, convolve_cuda_paralell_many_inputs

class Neural_Network:


  def __init__(self,num_nets,input_size,given_layers,loc=0,scale=1, cage_dimensionalities = None, use_bias=True):
    self.mempool = cp.get_default_memory_pool()
    self.pinned_mempool = cp.get_default_memory_pool()
    self.population_size = num_nets
    self.input_size = input_size
    self.input_layers = given_layers
    self.vectorized = False 
    self.layers = [] 
    self.matrix = None
    self.layers_shapes, self.input_sizes  = self.parse_input(given_layers,input_size,num_nets)
    self.dimensionality = self.compute_dimensionality()
    self.cage_dimensionalities = cage_dimensionalities
    self.use_bias = use_bias
    for layer in self.layers_shapes:
      if layer[0] == 'conv':
        self.layers.append(['conv', cp.random.normal(loc = loc, scale = scale, size = layer[1]).astype(cp.float32)])
      if layer[0] == 'linear':
        self.layers.append(['linear', cp.random.normal(loc = loc, scale = scale, size = layer[1]).astype(cp.float32)]) 
      if layer[0] == 'bias':
        self.layers.append(['bias', cp.zeros(shape = layer[1]).astype(cp.float32)])
  

  def cuda_memory_clear(self):
    self.mempool.free_all_blocks()
    self.pinned_mempool.free_all_blocks()    

  # every individual is getting trapnsfered to vector
  def parse_to_vector(self): 
    ret_mat = np.zeros((self.population_size, self.dimensionality),dtype = np.float32)
    index = 0
    for layer in self.layers:
      i = 0
      for individual in layer[1]:
        ret_mat[i][index:index+individual.size] = cp.asnumpy(individual.flatten())
        i += 1 
      index += layer[1][0].flatten().size
    self.layers = []
    self.cuda_memory_clear()
    self.matrix = cp.array(ret_mat, dtype = cp.float32)
    self.vectorized = True

  def list_memory_clear(self, lista):
    for _ in range(len(lista)):
      del lista[0]

  def parse_input(self,given_layers,input_size,num_nets):
    layers = []
    input_size = (input_size[0],input_size[1],input_size[2])
    input_sizes = []

    iterator = 1
    for layer in given_layers:
      print(layer, input_size, type(input_size))

      if layer[0] == 'conv':
        layers.append((layer[0],[num_nets,layer[1][0],input_size[0],layer[1][1],layer[1][2]]))
        input_sizes.append("placeholder")
        input_size = (layer[1][0],input_size[1]-layer[1][1]+1,input_size[2]-layer[1][2]+1)
        input_size = (input_size[0],np.floor(input_size[1]/2),np.floor(input_size[2]/2))
        input_size = tuple(map(lambda x:int(x), input_size))

      if layer[0] == 'linear':
        temp = 1
        if type(input_size) == int:
          temp = input_size
        else:
          temp = reduce( lambda a,b: a*b, input_size)
        input_size = int(temp)
        layers.append((layer[0],[num_nets,input_size,layer[1]]))
        input_sizes.append("placeholder")
        input_size = layer[1]

      if iterator != len(given_layers):
        if type(input_size) == int:
          layers.append(('bias', [num_nets] + [input_size]))
          input_sizes.append( [num_nets] + [input_size])
        else:
          layers.append(('bias', [num_nets, input_size[0], 1, 1] ))
          input_sizes.append([num_nets] + list(input_size))
      iterator += 1
      
      
    print("layers: ", layers)
    return layers, input_sizes
  
  def compute_dimensionality(self):
    number_of_weights = 0
    for layer_shape in self.layers_shapes:
      print("layer_shape: ", layer_shape)
      weights_in_layer = reduce(lambda a,b: a*b, layer_shape[1][1:])
      number_of_weights += weights_in_layer
    return number_of_weights



  def sample(self,B,D, sigma, mean, lam):
    self.layers = []
    self.cuda_memory_clear()
    #concat sampled vectors and parse them
    ret_mat = cp.zeros((lam, self.dimensionality),dtype = cp.float32)
    for i in range(lam):
      ret_mat[i] = self.multivariate_cholesky(mean,B,D,sigma)
      self.cuda_memory_clear()
    self.matrix = ret_mat
    self.vectorized = True

  def multivariate_cholesky(self,mean,B,D,sigma):
    vector = cp.random.normal(loc = 0,scale = 1,size = self.dimensionality,dtype = cp.float32)
    ret_val = sigma*B.dot(D*vector) + mean
    return ret_val

  def caged_sample(self,Bs,Ds, sigmas, means, lam):
    self.layers = []
    self.cuda_memory_clear()
    #concat sampled vectors and parse them
    ret_mat = cp.zeros((lam, self.dimensionality),dtype = cp.float32)
    for i in range(lam):
      ret_mat[i] = self.caged_multivariate_cholesky(means,Bs,Ds,sigmas)
    self.cuda_memory_clear()
    self.matrix = ret_mat
    self.vectorized = True
  
  def caged_multivariate_cholesky(self, means, Bs, Ds, sigmas):
    vector = cp.array([])
    for i in range(len(means)):
      sampled_vector = cp.random.normal(loc = 0,scale = 1,size = Bs[i].shape[0],dtype = cp.float32)
      sampled_vector = sigmas[i]*Bs[i].dot(Ds[i]*sampled_vector) + means[i]
      vector = cp.concatenate((vector, sampled_vector))
    return vector

  def mult(self, l):
    ret_val = 1
    for number in l:
      ret_val *= number
    return ret_val

  def parse_from_vectors(self):
    numbers = []
    self.matrix = cp.asnumpy(self.matrix)
    self.cuda_memory_clear()
    for layer in self.layers_shapes:
      print(layer[1])
      numbers.append(self.mult(layer[1][1:]))
    start = 0
    it = 0
    for number in numbers:
      self.layers.append((self.layers_shapes[it][0],cp.array(self.matrix[:,start:(start+number)]).reshape(self.layers_shapes[it][1])))
      it+=1
      start += number
    self.matrix = None
    self.vectorized = False

  def move_to_cpu(self):
    for layer in self.layers:
      layer[1] = cp.asnumpy(layer[1])

  def move_to_gpu(self):
    for layer in self.layers:
      layer[1] = cp.array(layer[1])

  def forward(self, state):
    layer_num = 0
    temp = state.copy()
    first_lin = 0
    for layer in self.layers:
      if layer[0]=='conv':
        if layer_num == 0:
          temp = convolve_cuda_paralell(temp, layer[1])
        else:
          temp = convolve_cuda_paralell_many_inputs(temp, layer[1])
        temp = max_pooling_cuda_paralell(temp)
      if layer[0]=='linear':
        if first_lin == 0:
          first_lin = 1
        temp = temp.flatten()
        if layer_num ==0:
          temp = dot_cuda_paralell(temp, layer[1])
        else:
          temp = dot_cuda_paralell_many_inputs(temp, layer[1])
      if layer[0] == 'bias':
        if self.use_bias:
           temp += layer[1]
        temp = cp.tanh(temp, dtype = cp.float32)
      layer_num += 1
    return cp.argmax(temp, axis = 1)

  def replace_individual(self, i, individual):
    i = int(i)
    for j in range(len(self.layers)):
      self.layers[j][1][i] = individual[j]
      self.list_memory_clear(individual)
    del individual

  def return_chosen_ones(self, indices, number_of_cage = None):
    if not self.vectorized:
        self.parse_to_vector()
    
    if number_of_cage == None:
      return self.matrix[indices]
    else:
      begin = self.cage_dimensionalities[:number_of_cage].sum()
      move = self.cage_dimensionalities[number_of_cage]
      return self.matrix[indices, begin : begin + move]
      