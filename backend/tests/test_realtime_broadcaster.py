"""
Unit tests for app/realtime/broadcaster.py - pure in-memory logic, no
database, no event loop dependency beyond asyncio.Queue/asyncio.run
itself. Covers: publish reaches every subscriber for the right
company_profile_id and nobody else, unsubscribe is idempotent, and
publishing to a workspace with zero connected subscribers is a
harmless no-op (the overwhelmingly common case in production - most
Events are published while nobody has a browser tab open).

Run standalone with:
    python -m unittest tests.test_realtime_broadcaster
"""
import asyncio
import unittest
import uuid

from app.realtime.broadcaster import Broadcaster


class TestRealtimeBroadcaster(unittest.TestCase):
    def test_publish_reaches_subscribed_queue(self):
        async def scenario():
            broadcaster = Broadcaster()
            company_id = uuid.uuid4()
            queue = broadcaster.subscribe(company_id)

            broadcaster.publish(company_id, {"event_type": "test.thing"})

            payload = await asyncio.wait_for(queue.get(), timeout=1)
            self.assertEqual(payload, {"event_type": "test.thing"})

        asyncio.run(scenario())

    def test_publish_does_not_cross_company_boundaries(self):
        async def scenario():
            broadcaster = Broadcaster()
            company_a = uuid.uuid4()
            company_b = uuid.uuid4()
            queue_a = broadcaster.subscribe(company_a)
            queue_b = broadcaster.subscribe(company_b)

            broadcaster.publish(company_a, {"event_type": "only.for.a"})

            payload = await asyncio.wait_for(queue_a.get(), timeout=1)
            self.assertEqual(payload, {"event_type": "only.for.a"})
            self.assertTrue(queue_b.empty())

        asyncio.run(scenario())

    def test_publish_with_no_subscribers_is_a_no_op(self):
        broadcaster = Broadcaster()
        # Must not raise, even though nobody has ever subscribed for
        # this company_profile_id.
        broadcaster.publish(uuid.uuid4(), {"event_type": "nobody.listening"})

    def test_multiple_subscribers_for_the_same_company_all_receive_it(self):
        async def scenario():
            broadcaster = Broadcaster()
            company_id = uuid.uuid4()
            queue_1 = broadcaster.subscribe(company_id)
            queue_2 = broadcaster.subscribe(company_id)

            broadcaster.publish(company_id, {"event_type": "fan.out"})

            self.assertEqual(await asyncio.wait_for(queue_1.get(), timeout=1), {"event_type": "fan.out"})
            self.assertEqual(await asyncio.wait_for(queue_2.get(), timeout=1), {"event_type": "fan.out"})

        asyncio.run(scenario())

    def test_unsubscribe_stops_further_delivery_and_is_idempotent(self):
        broadcaster = Broadcaster()
        company_id = uuid.uuid4()
        queue = broadcaster.subscribe(company_id)

        broadcaster.unsubscribe(company_id, queue)
        # Second unsubscribe of the same (already-removed) queue must
        # not raise - the route's `finally` block relies on this.
        broadcaster.unsubscribe(company_id, queue)

        broadcaster.publish(company_id, {"event_type": "after.unsubscribe"})
        self.assertTrue(queue.empty())

    def test_subscriber_count(self):
        broadcaster = Broadcaster()
        company_id = uuid.uuid4()
        self.assertEqual(broadcaster.subscriber_count(company_id), 0)

        queue = broadcaster.subscribe(company_id)
        self.assertEqual(broadcaster.subscriber_count(company_id), 1)

        broadcaster.unsubscribe(company_id, queue)
        self.assertEqual(broadcaster.subscriber_count(company_id), 0)


if __name__ == "__main__":
    unittest.main()
