import unittest

from src.app.config import settings
from src.app.services import logotypes_batch

TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakePipeline:
    def __init__(self, owner):
        self.owner = owner
        self.operations = []

    def setex(self, key, ttl, value):
        self.operations.append((key, ttl, value))
        return self

    async def execute(self):
        self.owner.setex_calls.extend(self.operations)


class _FakeRedis:
    def __init__(self):
        self.setex_calls = []
        self.delete_calls = []

    def pipeline(self):
        return _FakePipeline(self)

    async def delete(self, *keys):
        self.delete_calls.append(tuple(keys))


class LogotypesBatchCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake_redis = _FakeRedis()
        self.original_client = logotypes_batch._redis_client
        self.original_client_loop = logotypes_batch._redis_client_loop
        self.original_redis_class = logotypes_batch.RedisClient
        self.original_redis_url = settings.REDIS_URL

        logotypes_batch._redis_client = self.fake_redis
        logotypes_batch._redis_client_loop = None
        logotypes_batch.RedisClient = object
        settings.REDIS_URL = "redis://fake"

    async def asyncTearDown(self):
        logotypes_batch._redis_client = self.original_client
        logotypes_batch._redis_client_loop = self.original_client_loop
        logotypes_batch.RedisClient = self.original_redis_class
        settings.REDIS_URL = self.original_redis_url

    async def test_cache_logotype_data_writes_data_url_immediately(self):
        await logotypes_batch.cache_logotype_data(
            logotype_id=42,
            raw_data=TEST_PNG_BYTES,
        )

        self.assertEqual(len(self.fake_redis.setex_calls), 1)
        key, ttl, value = self.fake_redis.setex_calls[0]
        self.assertEqual(key, "active_org_logo:v1:42")
        self.assertEqual(ttl, settings.LOGO_CACHE_TTL_SECONDS)
        self.assertTrue(value.startswith("data:image/png;base64,"))

    async def test_invalidate_logotype_cache_deletes_keys(self):
        await logotypes_batch.invalidate_logotype_cache(logotype_ids=[7, 8, 8, 0, -1])

        self.assertEqual(
            self.fake_redis.delete_calls,
            [("active_org_logo:v1:7", "active_org_logo:v1:8")],
        )
