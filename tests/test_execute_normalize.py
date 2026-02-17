import unittest

from execute_normalize import (
    build_running_instances,
    normalize_execute_samples,
    require_scalar_streams,
)


class NormalizeExecuteSamplesTests(unittest.TestCase):
    def test_normalize_by_dim_id_paths(self):
        samples = [
            {"path": "/my_particle:0", "data": [0, 1, 2]},
            {"path": "/my_particle:1", "data": [1, 1, 1]},
            {"path": "/my_particle:2", "data": [60, 62, 64]},
            {"path": "/my_particle:3", "data": [90, 88, 86]},
            {"path": "/my_particle:4", "data": [3, 3, 3]},
            {"path": "/my_particle:5", "data": [4, 4, 4]},
        ]

        streams, unknown = normalize_execute_samples(samples)

        self.assertEqual(streams["time"], [0, 1, 2])
        self.assertEqual(streams["duration"], [1, 1, 1])
        self.assertEqual(streams["pitch"], [60, 62, 64])
        self.assertEqual(streams["velocity"], [90, 88, 86])
        self.assertEqual(streams["numerator"], [3, 3, 3])
        self.assertEqual(streams["denominator"], [4, 4, 4])
        self.assertEqual(unknown, [])

    def test_normalize_legacy_feature_path_fallback(self):
        samples = [
            {"feature_path": "/x/y/time", "data": [0, 2, 4]},
            {"feature_path": "/x/y/duration", "data": [2, 2, 2]},
            {"feature_path": "/x/y/pitch", "data": [70, 72, 74]},
            {"feature_path": "/x/y/velocity", "data": [100, 101, 102]},
            {"feature_path": "/x/y/numerator", "data": [4, 4, 4]},
            {"feature_path": "/x/y/denominator", "data": [4, 4, 4]},
        ]

        streams, unknown = normalize_execute_samples(samples)

        self.assertEqual(streams["time"], [0, 2, 4])
        self.assertEqual(streams["denominator"], [4, 4, 4])
        self.assertEqual(unknown, [])

    def test_require_scalar_streams_raises_on_missing(self):
        with self.assertRaises(RuntimeError) as ctx:
            require_scalar_streams({"time": [0]}, label="unitA bar01", unknown_paths=["/bad/path"])
        self.assertIn("Missing execute scalar streams", str(ctx.exception))


class BuildRunningInstancesTests(unittest.TestCase):
    def test_build_running_instances_matches_dim_order(self):
        seeds = {
            "time": 10,
            "duration": 2,
            "pitch": 60,
            "velocity": 90,
            "numerator": 3,
            "denominator": 4,
        }
        dims = [
            {"feature_name": "time"},
            {"feature_name": "duration"},
            {"feature_name": "pitch"},
            {"feature_name": "velocity"},
            {"feature_name": "numerator"},
            {"feature_name": "denominator"},
        ]

        instances = build_running_instances(seeds, dims)

        self.assertEqual(instances[0], {"start_point": 10, "transformation_shift": 0})
        self.assertEqual(instances[1], {"start_point": 10, "transformation_shift": 0})
        self.assertEqual(instances[2], {"start_point": 2, "transformation_shift": 0})
        self.assertEqual(instances[3], {"start_point": 60, "transformation_shift": 0})
        self.assertEqual(len(instances), 7)


if __name__ == "__main__":
    unittest.main()
