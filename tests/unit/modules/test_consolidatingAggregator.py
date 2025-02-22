import os
import json
from random import random, choice

from apiritif import random_string
from bzt.modules.aggregator import ConsolidatingAggregator, DataPoint, KPISet, AggregatorListener
from bzt.utils import to_json, BetterDict
from tests.unit import BZTestCase, EngineEmul
from tests.unit.mocks import r, MockReader


def get_success_reader(offset=0):
    mock = MockReader()
    mock.data.append((1 + offset, "first", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((2 + offset, "second", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((2 + offset, "first", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((3 + offset, "second", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((3 + offset, "first", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((4 + offset, "third", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((4 + offset, "first", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((6 + offset, "second", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((6 + offset, "third", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((6 + offset, "first", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((5 + offset, "first", 1, r(), r(), r(), 200, None, '', 0))
    return mock


def get_success_reader_alot(prefix='', offset=0):
    mock = MockReader()
    for x in range(2, 100):
        rnd = int(random() * x)
        mock.data.append((x + offset, prefix + random_string(1 + rnd), 1, r(), r(), r(), 200, '', '', 0))
    return mock


def get_success_reader_selected_labels(offset=0):
    mock = MockReader()
    labels = ['http://blazedemo.com/reserve.php',
              'http://blazedemo.com/purchase.php',
              'http://blazedemo.com/vacation.html',
              'http://blazedemo.com/confirmation.php',
              'http://blazedemo.com/another.php']
    for x in range(2, 200):
        mock.data.append((x + offset, choice(labels), 1, r(), r(), r(), 200, '', '', 0))
    return mock


def random_url(target_len):
    base = 'http://site.com/?foo='
    return base + random_string(target_len - len(base))


def get_success_reader_shrinking_labels(max_label_size=20, count=500):
    mock = MockReader()
    half_size = max_label_size // 2
    for x in range(2, count):
        target_size = max_label_size - int(float(half_size) * float(x) / float(count))
        label = random_url(target_size)
        mock.data.append((x, label, 1, r(), r(), r(), 200, '', '', 0))
    return mock


def get_fail_reader(offset=0):
    mock = MockReader()
    mock.data.append((1 + offset, "first", 1, r(), r(), r(), 200, 'FAILx3', '', 0))
    mock.data.append((2 + offset, "first", 1, r(), r(), r(), 200, 'FAILx1', '', 0))
    mock.data.append((5 + offset, "first", 1, r(), r(), r(), 200, None, '', 0))
    mock.data.append((7 + offset, "second", 1, r(), r(), r(), 200, 'FAILx3', '', 0))
    mock.data.append((3 + offset, "first", 1, r(), r(), r(), 200, 'FAILx3', '', 0))
    mock.data.append((6 + offset, "second", 1, r(), r(), r(), 200, 'unique FAIL', '', 0))
    return mock


def get_fail_reader_alot(offset=0):
    mock = MockReader()
    for x in range(2, 200):
        rnd = int(random() * x)
        mock.data.append((x + offset, "first", 1, r(), r(), r(), 200, (random_string(1 + rnd)), '', 0))
    return mock


class TestTools(BZTestCase):
    def test_mock(self):
        # check mock reader
        reader = get_success_reader()
        reader.buffer_scale_idx = '90.0'
        first = list(reader.datapoints())
        second = list(reader.datapoints(True))
        self.assertEquals([1, 2, 3, 4], [x[DataPoint.TIMESTAMP] for x in first])
        self.assertEquals([5, 6], [x[DataPoint.TIMESTAMP] for x in second])
        for point in first + second:
            self.assertIn("", point[DataPoint.CURRENT])

    def test_merging(self):
        dst = DataPoint(0)
        src = DataPoint(0)
        src[DataPoint.CUMULATIVE].setdefault('', KPISet())
        src[DataPoint.CUMULATIVE][''].sum_rt = 0.5

        src[DataPoint.CUMULATIVE][''][KPISet.SAMPLE_COUNT] = 1
        dst.merge_point(src)
        self.assertEquals(0.5, dst[DataPoint.CUMULATIVE][''].sum_rt)
        self.assertEquals(0.5, dst[DataPoint.CUMULATIVE][''][KPISet.AVG_RESP_TIME])

        src[DataPoint.CUMULATIVE][''][KPISet.SAMPLE_COUNT] = 3
        dst.merge_point(src)
        self.assertEquals(4, dst[DataPoint.CUMULATIVE][''][KPISet.SAMPLE_COUNT])
        self.assertEquals(1, dst[DataPoint.CUMULATIVE][''].sum_rt)
        self.assertEquals(0.25, dst[DataPoint.CUMULATIVE][''][KPISet.AVG_RESP_TIME])

        src[DataPoint.CUMULATIVE][''][KPISet.SAMPLE_COUNT] = 6
        dst.merge_point(src)
        self.assertEquals(10, dst[DataPoint.CUMULATIVE][''][KPISet.SAMPLE_COUNT])
        self.assertEquals(1.5, dst[DataPoint.CUMULATIVE][''].sum_rt)
        self.assertEquals(0.15, dst[DataPoint.CUMULATIVE][''][KPISet.AVG_RESP_TIME])


class TestConsolidatingAggregator(BZTestCase):
    def setUp(self):
        super(TestConsolidatingAggregator, self).setUp()
        self.obj = ConsolidatingAggregator()
        self.obj.engine = EngineEmul()

    def test_extend_data(self):
        self.obj.settings['extend-aggregation'] = True
        reader = MockReader()
        watcher = MockReader()

        reader.buffer_scale_idx = '100.0'
        # data format: t_stamp, label, conc, r_time, con_time, latency, r_code, error, trname, byte_count
        reader.data.append((1, "a", 1, 1, 1, 1, 200, None, '', 1))
        reader.data.append((2, "b", 1, 2, 2, 2, 200, 'OK', '', 2))
        reader.data.append((2, "b", 1, 3, 3, 3, 404, "Not Found", '', 3))
        reader.data.append((2, "c", 1, 4, 4, 4, 200, None, '', 4))
        reader.data.append((3, "d", 1, 5, 5, 5, 200, None, '', 5))
        reader.data.append((5, "b", 1, 6, 6, 6, 200, None, '', 6))
        reader.data.append((5, "c", 1, 7, 7, 7, 200, None, '', 7))

        self.obj.add_underling(reader)
        self.obj.add_listener(watcher)

        self.obj.prepare()
        self.obj.startup()
        self.obj.check()
        self.obj.shutdown()
        self.obj.post_process()

        converted_data = [self.obj.converter(dp) for dp in watcher.results]
        a, overall = (converted_data[0]["current"][key]["success"]["avg_rt"] for key in ("a", ""))
        self.assertEqual(a, overall)

        b, c, overall = (converted_data[-1]["current"][key]["success"]["avg_rt"] for key in ("b", "c", ""))
        self.assertEqual(overall, (b + c) / 2.0)

    def test_two_executions(self):
        self.obj.track_percentiles = [0, 50, 100]
        self.obj.prepare()
        underling1 = get_success_reader()
        underling2 = get_success_reader()
        self.obj.add_underling(underling1)
        self.obj.add_underling(underling2)

        cnt = 0
        for _ in range(1, 10):
            for point in self.obj.datapoints():
                self.assertEqual(2, len(point[DataPoint.SUBRESULTS]))
                overall = point[DataPoint.CURRENT]['']
                self.assertEquals(2, overall[KPISet.CONCURRENCY])
                self.assertGreater(overall[KPISet.PERCENTILES]["100.0"], 0)
                self.assertGreater(overall[KPISet.AVG_RESP_TIME], 0)
                cnt += 1

        self.assertEquals(2, cnt)

    def test_new_aggregator(self):
        # aggregator's config
        self.obj.extend_aggregation = True

        reader = MockReader()
        watcher = MockReader()

        # executor/reporter prepare level
        self.obj.add_underling(reader)
        self.obj.add_listener(watcher)

        # send rules to underlings
        self.obj.startup()

        reader.buffer_scale_idx = '100.0'
        # data format: t_stamp, label, conc, r_time, con_time, latency, r_code, error, trname, byte_count
        reader.data.append((1, "a", 1, 1, 1, 1, 200, None, '', 0))
        reader.data.append((2, "b", 1, 2, 2, 2, 200, 'OK', '', 0))
        reader.data.append((2, "b", 1, 3, 3, 3, 404, "Not Found", '', 0))
        reader.data.append((2, "c", 1, 4, 4, 4, 200, None, '', 0))
        reader.data.append((3, "d", 1, 5, 5, 5, 200, None, '', 0))
        reader.data.append((4, "b", 1, 6, 6, 6, 200, None, '', 0))

        # let's collect data to seconds and send something aggregated to watcher
        self.obj.shutdown()
        self.obj.post_process()

        data_points = watcher.results[-1][DataPoint.CUMULATIVE]
        self.assertEquals(7, len(data_points))
        sample_labels = {'a-success', 'b-success', 'b-jmeter_errors', 'b-http_errors', 'c-success', 'd-success', ''}
        self.assertEquals(sample_labels, set(data_points.keys()))

    def test_errors_cumulative(self):
        self.obj.track_percentiles = [50]
        self.obj.prepare()
        reader = get_fail_reader()
        self.obj.add_underling(reader)
        self.obj.shutdown()
        self.obj.post_process()
        cum_dict = self.obj.underlings[0].cumulative
        first_err_ids = [id(err) for err in cum_dict['first']['errors']]
        second_err_ids = [id(err) for err in cum_dict['second']['errors']]
        total_err_ids = [id(err) for err in cum_dict['']['errors']]
        all_ids = first_err_ids + second_err_ids + total_err_ids
        self.assertEqual(len(all_ids), len(set(all_ids)))
        for label in cum_dict:
            data = cum_dict[label]
            total_errors_count = sum(err['cnt'] for err in data['errors'])
            self.assertEqual(data['fail'], total_errors_count)

    def test_labels_variety(self):
        self.obj.track_percentiles = [50]
        self.obj.prepare()
        reader1 = get_success_reader()
        reader2 = get_success_reader_alot()
        self.obj.log.info(len(reader1.data) + len(reader2.data))
        self.obj.generalize_labels = 25
        self.obj.add_underling(reader1)
        self.obj.add_underling(reader2)
        self.obj.shutdown()
        self.obj.post_process()
        cum_dict = self.obj.cumulative
        len_limit = (self.obj.generalize_labels + 1)  # due to randomness, it it can go a bit higher than limit
        labels = list(cum_dict.keys())
        self.assertGreaterEqual(len(labels), self.obj.generalize_labels / 2)  # assert that it's at least half full
        self.assertLessEqual(len(labels), len_limit + 1)  # allow +1 label because '' is cumulative

    def test_labels_constant_part(self):
        self.obj.track_percentiles = [50]
        self.obj.prepare()
        reader = get_success_reader_alot(prefix='http://blazedemo.com/?r=')
        self.obj.log.info(len(reader.data))
        self.obj.generalize_labels = 25
        self.obj.add_underling(reader)
        self.obj.shutdown()
        self.obj.post_process()
        cum_dict = self.obj.cumulative
        labels = list(cum_dict.keys())
        self.assertGreaterEqual(len(labels), self.obj.generalize_labels / 2)  # assert that it's at least half full
        self.assertLessEqual(len(labels), self.obj.generalize_labels + 1)  # allow +1 label because '' is cumulative

    def test_labels_aggressive_folding(self):
        self.obj.track_percentiles = [50]
        self.obj.prepare()
        reader = get_success_reader_selected_labels()
        self.obj.log.info(len(reader.data))
        self.obj.generalize_labels = 25
        self.obj.add_underling(reader)
        self.obj.shutdown()
        self.obj.post_process()
        cum_dict = self.obj.cumulative
        labels = list(cum_dict.keys())
        self.assertEqual(len(labels), 6)

    def test_labels_aggressive_folding_2(self):
        self.obj.track_percentiles = [50]
        self.obj.prepare()
        label_count = 50
        reader = get_success_reader_shrinking_labels(max_label_size=int(label_count * 2), count=label_count)
        self.obj.log.info(len(reader.data))
        self.obj.generalize_labels = label_count
        self.obj.add_underling(reader)
        last = None
        for point in self.obj.datapoints(True):
            last = point
        cum_dict = self.obj.cumulative
        labels = list(cum_dict.keys())
        labels_count = len(labels)
        self.assertLessEqual(labels_count, label_count + 1)  # didn't overflow
        self.assertGreaterEqual(labels_count, label_count * 0.25)  # at least a quarter-filled
        self.assertEqual(1, len(last[DataPoint.SUBRESULTS]))
        self.assertEqual(last, last[DataPoint.SUBRESULTS][0])

    def test_errors_variety(self):
        self.obj.track_percentiles = [50]
        self.obj.prepare()
        reader1 = get_fail_reader()
        reader2 = get_fail_reader_alot()
        self.obj.max_error_count = 50
        self.obj.add_underling(reader1)
        self.obj.add_underling(reader2)
        self.obj.shutdown()
        self.obj.post_process()
        expected = self.obj.max_error_count  # due to randomness, it it can go a bit higher than limit
        self.assertLessEqual(len(self.obj.known_errors), expected)
        self.assertGreaterEqual(len(self.obj.known_errors),
                                self.obj.max_error_count / 2)  # assert that it's at least half full

    def test_uniq_errors(self):
        self.obj.track_percentiles = [50]
        self.obj.prepare()
        reader = get_fail_reader()
        self.obj.max_error_count = 9
        self.obj.add_underling(reader)
        self.obj.shutdown()
        self.obj.post_process()
        cum_dict = self.obj.cumulative
        self.assertEqual(len(cum_dict['']['errors']), 3)

    def test_set_rtimes_len(self):
        self.obj.settings['histogram-initial'] = 10.0
        self.obj.prepare()
        reader = get_fail_reader()
        self.obj.add_underling(reader)
        listener = MockListener()
        self.obj.add_listener(listener)
        self.obj.check()
        for dp in listener.results:
            for kpiset in dp['cumulative'].values():
                self.assertEqual(10000, kpiset[KPISet.RESP_TIMES].high)
            for kpiset in dp['current'].values():
                self.assertEqual(10000, kpiset[KPISet.RESP_TIMES].high)

    def test_inf_values(self):
        self.obj.settings['max-buffer-len'] = "inf"
        self.obj.prepare()
        self.assertEqual(self.obj.max_buffer_len, float("inf"))

    def test_datapoint_to_json(self):
        self.obj.track_percentiles = [0.0, 50.0, 95.0, 99.0, 100.0]
        self.obj.prepare()
        self.obj.add_underling(get_success_reader())
        for point in self.obj.datapoints():
            if point[DataPoint.SUBRESULTS] == [point]:
                del point[DataPoint.SUBRESULTS]
            self.obj.log.info(to_json(point))

    def test_negative_response_time_scaling_crash(self):
        self.obj.track_percentiles = [0.0, 50.0, 95.0, 99.0, 100.0]
        self.obj.prepare()

        self.sniff_log(self.obj.log)

        mock = MockReader()
        mock.data.append((1, "first", 1, -r(), r(), r(), 200, 'FAILx3', '', 0))
        mock.data.append((2, "first", 1, -r(), r(), r(), 200, 'FAILx1', '', 0))
        mock.data.append((5, "first", 1, -r(), r(), r(), 200, None, '', 0))
        mock.data.append((7, "second", 1, -r(), r(), r(), 200, 'FAILx3', '', 0))
        mock.data.append((3, "first", 1, -r(), r(), r(), 200, 'FAILx3', '', 0))
        mock.data.append((6, "second", 1, -r(), r(), r(), 200, 'unique FAIL', '', 0))

        self.obj.add_underling(mock)

        self.obj.check()
        for point in self.obj.datapoints():
            self.obj.log.info(to_json(point))

        self.assertIn("Negative response time reported", self.log_recorder.warn_buff.getvalue())

    def test_ramp_up_exclude(self):
        self.obj.track_percentiles = [50]
        self.obj.prepare()
        self.obj.engine.config['settings']['ramp-up-exclude'] = True
        self.obj.engine.config['execution'] = [
            {'scenario': 'first', 'ramp-up': 50},
            {'scenario': 'second', 'ramp-up': '1s'},
            {'scenario': 'third'}
        ]
        self.obj.engine.config['scenarios'] = BetterDict.from_dict({
            'first': {'requests': [{'url': 'first'}]},
            'second': {'requests': [{'url': 'second'}]},
            'third': {'requests': [{'url': 'third'}]}})
        reader = get_success_reader()
        self.obj.add_underling(reader)
        self.obj.shutdown()
        self.obj.post_process()
        self.assertEquals(self.obj.cumulative, {})


class MockListener(AggregatorListener):
    def __init__(self):
        super(MockListener, self).__init__()
        self.results = []

    def aggregated_second(self, data):
        self.results.append(data)
