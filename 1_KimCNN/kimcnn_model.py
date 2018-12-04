"""KimCNN - baseline in deep text classification."""
import tensorflow as tf


class KimCNN(object):
  """The cnn model of text classification."""
  def __init__(self, num_classes, seq_len, embedding_size, filter_sizes, num_filters, weight_decay,
               init_lr, decay_steps, decay_rate, vocab_size, is_rand=False, is_finetuned=False,
               embeddings=None):
    
    # parameters init
    self.num_classes = num_classes
    self.seq_len = seq_len
    self.embedding_size = embedding_size
    self.filter_sizes = filter_sizes
    self.num_filters = num_filters
    self.vocab_size = vocab_size
    self.is_rand = is_rand
    self.is_finetuned = is_finetuned
    self.embeddings = embeddings

    # weight decay
    self.weight_decay = weight_decay
    self.dropout_rate = tf.placeholder(tf.float32, name="dropout_rate")
    self.global_step = tf.Variable(0, trainable=False)
    self.add_global = self.global_step.assign_add(1)
    self.learning_rate = tf.train.exponential_decay(init_lr, global_step=self.global_step, 
                                                    decay_steps=decay_steps, decay_rate=decay_rate)

    self.model(), self.loss_acc(), self.train_op()

  def model(self):
    # word embeddings -> cnn (filter * k) -> fc -> logits
    self.inputs = tf.placeholder(tf.int32, [None, self.seq_len], name='inputs')
    self.labels = tf.placeholder(tf.float32, [None, self.num_classes], name='labels')

    # words embeddings
    with tf.device("/gpu:0"):
      if self.is_rand:
        W = tf.Variable(tf.truncated_normal([self.vocab_size, self.embedding_size], 
                                            stddev=0.1), name="W")
      else:
        W = tf.get_variable(name='W', trainable=self.is_finetuned,
                            shape=[self.vocab_size, self.embedding_size], 
                            initializer=tf.constant_initializer(self.embeddings))

    embedded_chars = tf.nn.embedding_lookup(W, self.inputs)
    embedded_chars_expanded = tf.expand_dims(embedded_chars, -1)

    # pool layer
    pooled_outputs = []
    for i, filter_size in enumerate(self.filter_sizes):
      with tf.name_scope("conv-maxpool-%s" % filter_size):
        W = tf.Variable(tf.truncated_normal(
          [filter_size, self.embedding_size, 1, self.num_filters], stddev=0.1), name='W')
        b = tf.Variable(tf.constant(0.1, shape=[self.num_filters]), name='bias')
        conv = tf.nn.conv2d(embedded_chars_expanded, W, 
                            strides=[1, 1, 1, 1], padding='VALID', name='conv')
        h = tf.nn.relu(tf.nn.bias_add(conv, b), name="relu")
        pooled = tf.nn.max_pool(h, 
                                ksize=[1, self.seq_len - filter_size + 1, 1, 1], 
                                strides=[1, 1, 1, 1], padding='VALID', name='pool')
        pooled_outputs.append(pooled)

    num_filters_total = self.num_filters * len(self.filter_sizes)
    h_pool = tf.concat(pooled_outputs, 3)
    h_pool_flat = tf.reshape(h_pool, [-1, num_filters_total])
    h_drop = tf.nn.dropout(h_pool_flat, self.dropout_rate)

    with tf.name_scope("inference"):
      W = tf.Variable(tf.truncated_normal(
        [num_filters_total, self.num_classes], stddev=0.1), name='W')
      b = tf.Variable(tf.constant(0.1, shape=[self.num_classes]), name='bias')
      self.logits = tf.nn.xw_plus_b(h_drop, W, b, name='logits')
      self.predictions = tf.argmax(self.logits, 1, name='predictions')

  def loss_acc(self):

    with tf.name_scope("loss"):
      # losses = tf.nn.softmax_cross_entropy_with_logits(labels=self.labels, logits=self.logits)
      losses = tf.nn.sigmoid_cross_entropy_with_logits(labels=self.labels, logits=self.logits)
      
      # exculde the biases parameters
      self.loss = tf.add(tf.reduce_mean(losses), 
        self.weight_decay * tf.add_n(
          [tf.nn.l2_loss(v) for v in tf.trainable_variables() if 'bias' not in v.name]))

    with tf.name_scope("accuracy"):
      correct_predictions = tf.equal(self.predictions, tf.argmax(self.labels, 1))
      self.accuracy = tf.reduce_mean(tf.cast(correct_predictions, "float"), name='accuracy')

  def train_op(self):
    
    optimizer = tf.train.AdamOptimizer(self.learning_rate)
    grads_and_vars = optimizer.compute_gradients(self.loss)
    # grads_and_vars = [(tf.clip_by_value(grad, -1., 1.), var) 
    #  for grad, var in grads_and_vars]
    self.optimization = optimizer.apply_gradients(grads_and_vars)