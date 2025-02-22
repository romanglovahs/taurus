from bzt.modules.aggregator import DataPoint, KPISet, ConsolidatingAggregator
from bzt.modules.external import ExternalResultsLoader
from bzt.modules.jmeter import FuncJTLReader, JTLReader
from bzt.modules.ab import TSVDataReader
from bzt.modules.gatling import DataLogReader as GatlingLogReader
from bzt.modules.vegeta import VegetaLogReader

from tests.unit import RESOURCES_DIR, close_reader_file, ExecutorTestCase
from tests.unit.mocks import MockReader


class TestExternalResultsLoader(ExecutorTestCase):
    EXECUTOR = ExternalResultsLoader

    def tearDown(self):
        if self.obj.reader:
            if isinstance(self.obj.reader, FuncJTLReader):
                close_reader_file(self.obj.reader)
            if isinstance(self.obj.reader, JTLReader):
                close_reader_file(self.obj.reader.csvreader)
                close_reader_file(self.obj.reader.errors_reader)
        super(TestExternalResultsLoader, self).tearDown()

    def configure(self, config):
        super(TestExternalResultsLoader, self).configure(config)
        self.results_listener = MockReader()
        self.obj.engine.aggregator = ConsolidatingAggregator()
        self.obj.engine.aggregator.engine = self.obj.engine
        self.obj.engine.aggregator.add_listener(self.results_listener)

    def test_no_data_file(self):
        self.configure({
            "execution": [{
                # empty execution
            }]
        })
        self.assertRaises(AssertionError, self.obj.prepare)

    def test_plain(self):
        self.configure({
            "execution": [{
                "data-file": RESOURCES_DIR + "/jmeter/jtl/simple.kpi.jtl"
            }]
        })
        self.obj.prepare()
        self.assertIsInstance(self.obj.reader, JTLReader)
        self.obj.startup()
        self.obj.check()
        self.obj.shutdown()
        self.obj.post_process()
        self.obj.engine.aggregator.post_process()
        results = self.results_listener.results
        self.assertGreater(len(results), 0)
        last_dp = results[-1]
        cumulative_kpis = last_dp[DataPoint.CUMULATIVE]['']
        self.assertIn('200', cumulative_kpis[KPISet.RESP_CODES])

    def test_errors_jtl(self):
        self.configure({
            "execution": [{
                "data-file": RESOURCES_DIR + "/jmeter/jtl/simple.kpi.jtl",
                "errors-file": RESOURCES_DIR + "/jmeter/jtl/simple.error.jtl",
            }]
        })
        self.obj.prepare()
        self.obj.startup()
        self.obj.check()
        self.obj.shutdown()
        self.obj.post_process()
        self.obj.engine.aggregator.post_process()
        results = self.results_listener.results
        self.assertGreater(len(results), 0)
        last_dp = results[-1]
        cumulative_kpis = last_dp[DataPoint.CUMULATIVE]['']
        self.assertIn('200', cumulative_kpis[KPISet.RESP_CODES])
        self.assertIn('404', cumulative_kpis[KPISet.RESP_CODES])

    def test_errors_jtl2(self):
        self.configure({
            "execution": [{
                "data-file": RESOURCES_DIR + "/jmeter/jtl/kpi-pair1.jtl",
                "errors-file": RESOURCES_DIR + "/jmeter/jtl/error-pair1.jtl",
            }]
        })
        self.obj.prepare()
        self.obj.startup()
        cnt = 0
        while not self.obj.check():
            self.engine.aggregator.check()
            cnt += 1
            self.assertLess(cnt, 10)
        self.obj.shutdown()
        self.obj.post_process()
        self.obj.engine.aggregator.post_process()
        results = self.results_listener.results
        self.assertGreater(len(results), 0)
        last_dp = results[-1]
        cumulative_kpis = last_dp[DataPoint.CUMULATIVE]['']
        self.assertEqual(8, cumulative_kpis[KPISet.SAMPLE_COUNT])

    def test_execution_file_parsing(self):
        datafile_pair = RESOURCES_DIR + "jmeter/jtl/kpi-pair2.jtl"
        errorfile_pair = RESOURCES_DIR + "jmeter/jtl/error-pair2.jtl"
        self.configure({
            "execution": [{
                "data-file": datafile_pair,
                "errors-file": errorfile_pair,
            }]
        })
        self.obj.prepare()
        self.assertEqual(datafile_pair.replace('\\', '/'), self.obj.data_file.replace('\\', '/'))
        self.assertEqual(errorfile_pair.replace('\\', '/'), self.obj.errors_file.replace('\\', '/'))

    def test_execution_parsing_priority(self):
        datafile_pair = RESOURCES_DIR + "jmeter/jtl/kpi-pair1.jtl"
        errorfile_pair = RESOURCES_DIR + "jmeter/jtl/error-pair1.jtl"
        another_datafile_pair = RESOURCES_DIR + "jmeter/jtl/kpi-pair2.jtl"
        another_errorfile_pair = RESOURCES_DIR + "jmeter/jtl/error-pair2.jtl"
        self.configure({
            "execution": [{
                "data-file": datafile_pair,
                "errors-file": errorfile_pair,
                "scenario": "sample"
            }],
            "scenarios": {
                "sample": {
                    "data-file": another_datafile_pair,
                    "errors-file": another_errorfile_pair,
                }
            }
        })
        self.obj.prepare()
        self.assertEqual(datafile_pair.replace('\\', '/'), self.obj.data_file.replace('\\', '/'))
        self.assertEqual(errorfile_pair.replace('\\', '/'), self.obj.errors_file.replace('\\', '/'))


    def test_ab(self):
        self.configure({
            "execution": [{
                "data-file": RESOURCES_DIR + "/ab/ab.tsv"
            }]
        })
        self.obj.prepare()
        self.assertIsInstance(self.obj.reader, TSVDataReader)
        self.obj.startup()
        self.obj.check()
        self.obj.shutdown()
        self.obj.post_process()
        self.obj.engine.aggregator.post_process()
        results = self.results_listener.results
        self.assertGreater(len(results), 0)
        last_dp = results[-1]
        cumulative_kpis = last_dp[DataPoint.CUMULATIVE]['']
        self.assertEqual(10, cumulative_kpis[KPISet.SUCCESSES])

    def test_gatling(self):
        self.configure({
            "execution": [{
                "data-file": RESOURCES_DIR + "/gatling/gatling-3-000/simulation.log",
            }]
        })
        self.obj.prepare()
        self.assertIsInstance(self.obj.reader, GatlingLogReader)
        self.obj.startup()
        self.obj.check()
        self.obj.shutdown()
        self.obj.post_process()
        self.obj.engine.aggregator.post_process()
        results = self.results_listener.results
        self.assertGreater(len(results), 0)
        last_dp = results[-1]
        cumulative_kpis = last_dp[DataPoint.CUMULATIVE]['']
        self.assertEqual(243, cumulative_kpis[KPISet.SUCCESSES])

    def test_vegeta(self):
        self.configure({
            "execution": [{
                "data-file": RESOURCES_DIR + "/vegeta/vegeta_kpi.csv",
            }]
        })
        self.obj.prepare()
        self.assertIsInstance(self.obj.reader, VegetaLogReader)
        self.obj.startup()
        self.obj.check()
        self.obj.shutdown()
        self.obj.post_process()
        self.obj.engine.aggregator.post_process()
        results = self.results_listener.results
        self.assertGreater(len(results), 0)
        last_dp = results[-1]
        cumulative_kpis = last_dp[DataPoint.CUMULATIVE]['']
        self.assertEqual(4, cumulative_kpis[KPISet.SUCCESSES] + cumulative_kpis[KPISet.FAILURES])
