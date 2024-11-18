import numpy as np
from typing_extensions import override

from lenskit.data.items import ItemList

from ._base import ListMetric, RankingMetricBase


class Precision(ListMetric, RankingMetricBase):
    """
    Compute recommendation precision.  This is computed as:

    .. math::
        \\frac{|L \\cap I_u^{\\mathrm{test}}|}{|L|}

    In the uncommon case that ``k`` is specified and ``len(recs) < k``, this metric uses
    ``len(recs)`` as the denominator.
    """

    @property
    def label(self):
        if self.k is not None:
            return f"Precision@{self.k}"
        else:
            return "Precision"

    @override
    def measure_list(self, recs: ItemList, test: ItemList) -> float:
        recs = self.truncate(recs)
        nrecs = len(recs)
        if nrecs == 0:
            return np.nan

        items = recs.ids()
        ngood = np.isin(items, test.ids()).sum()
        return ngood / nrecs


class Recall(ListMetric, RankingMetricBase):
    """
    Compute recommendation recall.  This is computed as:

    .. math::
        \\frac{|L \\cap I_u^{\\mathrm{test}}|}{\\operatorname{min}\\{|I_u^{\\mathrm{test}}|, k\\}}
    """

    @property
    def label(self):
        if self.k is not None:
            return f"Recall@{self.k}"
        else:
            return "Recall"

    @override
    def measure_list(self, recs: ItemList, test: ItemList) -> float:
        recs = self.truncate(recs)

        items = recs.ids()
        ngood = np.isin(items, test.ids()).sum()
        nrel = len(test)
        if self.k is not None and self.k < nrel:
            nrel = self.k
        return ngood / nrel
