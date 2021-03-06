# coding=utf-8

import tensorflow as tf
import logging
import os

from algorithm import config
from base.env.finance import Market
from base.nn.model import BaseSLTFModel
from checkpoints import CHECKPOINTS_DIR
from helper.args_parser import model_launcher_parser


class Algorithm(BaseSLTFModel):
    def __init__(self, session, env, seq_length, x_space, y_space, **options):
        super(Algorithm, self).__init__(session, env, **options)

        self.seq_length, self.x_space, self.y_space = seq_length, x_space, y_space

        try:
            self.hidden_size = options['hidden_size']
        except KeyError:
            self.hidden_size = 1

        self._init_input()
        self._init_nn()
        self._init_op()
        self._init_saver()

    def _init_input(self):
        self.x = tf.placeholder(tf.float32, [None, self.seq_length, self.x_space])
        self.label = tf.placeholder(tf.float32, [None, self.y_space])

    def _init_nn(self):
        # First Attn
        with tf.variable_scope("1st_encoder"):
            self.f_encoder_rnn = self.add_rnn(1, self.hidden_size)
            self.f_encoder_outputs, _ = tf.nn.dynamic_rnn(self.f_encoder_rnn, self.x, dtype=tf.float32)
            self.f_attn_inputs = tf.nn.softmax(self.f_encoder_outputs)
            self.f_attn_outputs = self.add_fc(self.f_attn_inputs, self.hidden_size, tf.tanh)
        with tf.variable_scope("1st_decoder"):
            self.f_decoder_input = tf.matmul(self.f_encoder_outputs, self.f_attn_outputs, transpose_a=True)
            self.f_decoder_rnn = self.add_rnn(1, self.hidden_size)
            self.f_decoder_outputs, _ = tf.nn.dynamic_rnn(self.f_decoder_rnn, self.f_decoder_input, dtype=tf.float32)
        # Second Attn
        with tf.variable_scope("2nd_encoder"):
            self.s_attn_input = tf.nn.softmax(self.f_decoder_outputs)
            self.s_attn_outputs = self.add_fc(self.s_attn_input, self.hidden_size, tf.tanh)
        with tf.variable_scope("2nd_decoder"):
            self.s_decoder_input = tf.matmul(self.f_decoder_outputs, self.s_attn_outputs, transpose_a=True)
            self.s_decoder_rnn = self.add_rnn(2, self.hidden_size)
            self.f_decoder_outputs, _ = tf.nn.dynamic_rnn(self.s_decoder_rnn, self.s_decoder_input, dtype=tf.float32)
            self.y = self.add_fc(self.f_decoder_outputs[:, -1], self.y_space)

    def _init_op(self):
        self.loss = tf.losses.mean_squared_error(self.y, self.label)
        self.global_step = tf.Variable(0, trainable=False)
        self.optimizer = tf.train.RMSPropOptimizer(self.learning_rate)
        self.train_op = self.optimizer.minimize(self.loss)
        self.session.run(tf.global_variables_initializer())

    def train(self):
        for step in range(self.train_steps):
            batch_x, batch_y = self.env.get_stock_batch_data(self.batch_size)
            _, loss = self.session.run([self.train_op, self.loss], feed_dict={self.x: batch_x, self.label: batch_y})
            if (step + 1) % 1000 == 0:
                logging.warning("Step: {0} | Loss: {1:.7f}".format(step + 1, loss))
            if step > 0 and (step + 1) % self.save_step == 0:
                if self.enable_saver:
                    self.save(step)


def main(args):
    env = Market(args.codes, **{"use_sequence": True})
    algorithm = Algorithm(tf.Session(config=config), env, env.seq_length, env.data_dim, env.code_count, **{
        # "mode": args.mode,
        "mode": "test",
        "log_level": args.log_level,
        "save_path": os.path.join(CHECKPOINTS_DIR, "SL", "DualAttnRNN", "model"),
        "enable_saver": True,
    })
    algorithm.run()
    algorithm.eval_and_plot()


if __name__ == '__main__':
    main(model_launcher_parser.parse_args())
