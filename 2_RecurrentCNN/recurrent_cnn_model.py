"""
  gfaia - gutianfeigtf@163.com
"""
import tensorflow as tf
from tensorflow.contrib import rnn


class ReccurentCNN(object):
  """the model based on the rnn or lstm."""
  def __init__(self, 
               num_classes, seq_len, embedding_size, vocab_size, rnn_size,
               weight_decay, init_lr, decay_steps, decay_rate, 
               is_rand=False, is_finetuned=False, embeddings=None):

    # parameters init
    self.num_classes = num_classes
    self.seq_len = seq_len
    self.embedding_size = embedding_size
    self.vocab_size = vocab_size
    self.rnn_size = rnn_size

    self.is_rand = is_rand
    self.is_finetuned = is_finetuned
    self.embeddings = embeddings

    # weight decay
    self.weight_decay = weight_decay
    self.dropout_rate = tf.placeholder(tf.float32, name="dropout_rate")
    self.global_step = tf.Variable(0, trainable=False)
    self.add_global = self.global_step.assign_add(1)
    self.learning_rate = tf.train.exponential_decay(init_lr, 
                                                    global_step=self.global_step, 
                                                    decay_steps=decay_steps, 
                                                    decay_rate=decay_rate)

    self.model(), self.loss_acc(), self.train_op()

  def model(self):
    # word embeddings -> bidirectional lstm, identity map  -> max pooling -> fc
    self.inputs = tf.placeholder(tf.int32, [None, self.seq_len], name='inputs')
    self.labels = tf.placeholder(tf.int32, [None], name='labels')
    self.onehot_labels = tf.one_hot(self.labels, self.num_classes)

    # word embeddings
    with tf.device('/gpu:0'):
      if self.is_rand:
        W = tf.Variable(tf.truncated_normal([self.vocab_size, self.embedding_size], 
                                            stddev=0.1), name="W")
      else:
        W = tf.get_variable(name='W', trainable=self.is_finetuned, 
                            shape=[self.vocab_size, self.embedding_size], 
                            initializer=tf.constant_initializer(self.embeddings))
    
    # embedding words
    embedded = tf.nn.embedding_lookup(W, self.inputs, "embedded")

    # bi-lstm layer, identity map
    lstm_fw_cell = rnn.BasicLSTMCell(self.rnn_size)
    lstm_bw_cell = rnn.BasicLSTMCell(self.rnn_size)
    if self.dropout_rate is not None:
      lstm_fw_cell = rnn.DropoutWrapper(lstm_fw_cell, output_keep_prob=self.dropout_rate)
      lstm_bw_cell = rnn.DropoutWrapper(lstm_bw_cell, output_keep_prob=self.dropout_rate)

    outputs, enc_state = tf.nn.bidirectional_dynamic_rnn(lstm_fw_cell, lstm_bw_cell, 
                                                         embedded, dtype=tf.float32)

    # forward, reverse direction lstm outputs
    forward_outputs, reverse_outputs = outputs
    # concat the forward, reverse, original
    final_outputs = tf.concat([forward_outputs, embedded, reverse_outputs], 2)
    # reduce_mean max pooling
    feature = tf.reduce_max(final_outputs, axis=1)
    
    # feature = tf.reduce_mean(final_outputs, axis=1)
    outputs_mean_dim = int(feature.shape[1])

    # inference layer
    with tf.name_scope("inference"):
      w = tf.Variable(tf.truncated_normal(shape=[outputs_mean_dim, self.num_classes], 
                                          mean=0, stddev=0.1), name="w")
      b = tf.Variable(tf.constant(value=0.1, shape=[self.num_classes]), name="bias")
      self.logits = tf.add(tf.matmul(feature, w), b)

  def loss_acc(self):
    """the loss and accuracy of model"""
    with tf.name_scope("loss"):
      losses = tf.nn.softmax_cross_entropy_with_logits(labels=self.onehot_labels, 
                                                       logits=self.logits)
      # exculde the bias parameters
      self.loss = tf.add(tf.reduce_mean(losses), self.weight_decay * tf.add_n(
        [tf.nn.l2_loss(v) for v in tf.trainable_variables() if 'bias' not in v.name]))

    with tf.name_scope("accuracy"):
      self.predictions = tf.argmax(self.logits, 1, name='predictions')
      correct_predictions = tf.equal(self.predictions, tf.argmax(self.onehot_labels, 1))
      self.accuracy = tf.reduce_mean(tf.cast(correct_predictions, "float"), name='accuracy')

  def train_op(self):
    
    optimizer = tf.train.AdamOptimizer(self.learning_rate)
    grads_and_vars = optimizer.compute_gradients(self.loss)
    # grads_and_vars = [(tf.clip_by_value(grad, -1., 1.), var) 
    #  for grad, var in grads_and_vars]
    self.optimization = optimizer.apply_gradients(grads_and_vars)
