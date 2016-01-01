from itertools import chain

import theano
import theano.tensor as T
from theano.ifelse import ifelse
import numpy as np

from neupy.utils import asfloat
from neupy.core.properties import BoundedProperty
from neupy.algorithms import GradientDescent


__all__ = ('LevenbergMarquardt',)


def jaccobian(y, x):
    n_samples = y.shape[0]
    J, _ = theano.scan(
        lambda i, y, *params: T.grad(T.sum(y[i]), wrt=params),
        sequences=T.arange(n_samples),
        non_sequences=[y] + x
    )

    jacc = []
    for j, param in zip(J, x):
        jacc.append(j.reshape((n_samples, param.size)))

    return T.concatenate(jacc, axis=1)


class LevenbergMarquardt(GradientDescent):
    """ Levenberg-Marquardt algorithm.

    Notes
    -----
    * Network minimizes only Mean Squared Error function.

    Parameters
    ----------
    mu : float
        Control invertion for J.T * J matrix, defaults to `0.1`.
    mu_update_factor : float
        Factor to decrease the mu if update decrese the error, otherwise
        increse mu by the same factor.
    {GradientDescent.optimizations}
    {ConstructableNetwork.connection}
    {BaseNetwork.step}
    {BaseNetwork.show_epoch}
    {BaseNetwork.shuffle_data}
    {BaseNetwork.epoch_end_signal}
    {BaseNetwork.train_end_signal}
    {Verbose.verbose}

    Methods
    -------
    {BaseSkeleton.predict}
    {SupervisedLearning.train}
    {BaseSkeleton.fit}
    {BaseNetwork.plot_errors}
    {BaseNetwork.last_error}
    {BaseNetwork.last_validation_error}
    {BaseNetwork.previous_error}

    Examples
    --------
    Simple example

    >>> import numpy as np
    >>> from neupy import algorithms
    >>>
    >>> x_train = np.array([[1, 2], [3, 4]])
    >>> y_train = np.array([[1], [0]])
    >>>
    >>> lmnet = algorithms.LevenbergMarquardt(
    ...     (2, 3, 1),
    ...     verbose=False
    ... )
    >>> lmnet.train(x_train, y_train)

    Diabets dataset example

    >>> import numpy as np
    >>> from sklearn import datasets, preprocessing
    >>> from sklearn.cross_validation import train_test_split
    >>> from neupy import algorithms, layers
    >>> from neupy.functions import rmsle
    >>>
    >>> dataset = datasets.load_diabetes()
    >>> data, target = dataset.data, dataset.target
    >>>
    >>> data_scaler = preprocessing.MinMaxScaler()
    >>> target_scaler = preprocessing.MinMaxScaler()
    >>>
    >>> x_train, x_test, y_train, y_test = train_test_split(
    ...     data_scaler.fit_transform(data),
    ...     target_scaler.fit_transform(target),
    ...     train_size=0.85
    ... )
    >>>
    >>> # Network
    ... lmnet = algorithms.LevenbergMarquardt(
    ...     connection=[
    ...         layers.Sigmoid(10),
    ...         layers.Sigmoid(40),
    ...         layers.Output(1),
    ...     ],
    ...     mu_update_factor=2,
    ...     mu=0.1,
    ...     step=0.25,
    ...     show_epoch=10,
    ...     use_bias=False,
    ...     verbose=False
    ... )
    >>> lmnet.train(x_train, y_train, epochs=100)
    >>> y_predict = lmnet.predict(x_test)
    >>>
    >>> error = rmsle(target_scaler.inverse_transform(y_test),
    ...               target_scaler.inverse_transform(y_predict).round())
    >>> error
    0.47548200957888398

    See Also
    --------
    :network:`GradientDescent` : GradientDescent algorithm.
    """

    mu = BoundedProperty(default=0.01, minval=0)
    mu_update_factor = BoundedProperty(default=5, minval=1)

    def init_properties(self):
        del self.step
        self.error = 'mse'
        return super(LevenbergMarquardt, self).init_properties()

    def init_variables(self):
        super(LevenbergMarquardt, self).init_variables()
        self.variables.update(
            mu=theano.shared(name='mu', value=asfloat(self.mu)),
            last_error=theano.shared(name='last_error', value=np.nan),
        )

    def init_train_updates(self):
        network_output = self.variables.network_output
        prediction_func = self.variables.prediction_func
        last_error = self.variables.last_error
        error_func = self.variables.error_func
        mu = self.variables.mu

        new_mu = ifelse(
            T.lt(last_error, error_func),
            mu * self.mu_update_factor,
            mu / self.mu_update_factor,
        )

        err = T.mean((network_output - prediction_func) ** 2, axis=1)

        params = list(
            chain(*[layer.parameters for layer in self.train_layers])
        )
        param_vector = T.concatenate([param.flatten() for param in params])
        J = jaccobian(err, params)
        n_params = J.shape[1]

        updated_params = param_vector - T.nlinalg.matrix_inverse(
            J.T.dot(J) + new_mu * T.eye(n_params)
        ).dot(J.T).dot(err)

        start_pos = 0
        updates = [(mu, new_mu)]
        for param in params:
            end_pos = start_pos + param.size

            updates.append((param, T.reshape(
                updated_params[start_pos:end_pos],
                param.shape
            )))

            start_pos = end_pos

        return updates

    def epoch_start_update(self, epoch):
        super(LevenbergMarquardt, self).epoch_start_update(epoch)

        last_error = self.last_error()
        if last_error is not None:
            self.variables.last_error.set_value(last_error)
