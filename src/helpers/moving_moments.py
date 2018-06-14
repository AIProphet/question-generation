import numpy as np

class MovingMoment:

    def __init__(self, rate=0.9):
        self.rate=0.9
        self._mean=None
        self._var=None

    def push(self, batch):
        self._mean = np.mean(batch) if self._mean is None else self.rate*self._mean + (1-self.rate)*np.mean(batch)
        self._var = np.var(batch) if self._var is None else self.rate*self._var + (1-self.rate)*np.var(batch-self._mean)

    @property
    def mean(self):
        return self._mean

    @property
    def variance(self):
        return self._var


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    mm = MovingMoment(0.9)

    means=[]
    vars=[]

    for i in range(1000):
        rand = np.random.normal(10,2,10)
        mm.push(rand)
        means.append(mm.mean)
        vars.append(mm.variance)

    plt.figure()
    plt.plot([x for x in range(1000)], means)
    plt.plot([x for x in range(1000)], vars)
    plt.show()
