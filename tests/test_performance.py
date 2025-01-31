"""
Performance and load testing for the payment system.
"""
import pytest
import asyncio
import time
import concurrent.futures
from unittest.mock import patch
import statistics

@pytest.mark.performance
class TestAPIPerformance:
    @pytest.mark.slow
    def test_concurrent_payment_processing(self, client, test_user, mock_stripe):
        """Test system performance under concurrent payment processing."""
        num_requests = 50
        start_time = time.time()
        
        async def make_payment_request():
            data = {
                'package_id': 'starter',
                'currency': 'usd'
            }
            with patch('stripe.PaymentIntent.create') as mock_create:
                mock_create.return_value = {
                    'id': f'pi_test_{time.time()}',
                    'client_secret': 'secret_test',
                    'status': 'requires_payment_method'
                }
                response = client.post(
                    '/api/v1/payments/create-intent',
                    json=data,
                    headers={'Authorization': f'Bearer {test_user.create_token()}'}
                )
                return response.status_code
        
        async def run_concurrent_requests():
            tasks = [make_payment_request() for _ in range(num_requests)]
            results = await asyncio.gather(*tasks)
            return results
        
        results = asyncio.run(run_concurrent_requests())
        end_time = time.time()
        
        # Calculate metrics
        total_time = end_time - start_time
        success_rate = results.count(200) / len(results)
        avg_request_time = total_time / num_requests
        
        # Assertions
        assert success_rate >= 0.95  # 95% success rate
        assert avg_request_time < 0.5  # Less than 500ms per request

    @pytest.mark.slow
    def test_webhook_processing_throughput(self, client, webhook_handler, sample_webhook_events):
        """Test webhook processing throughput."""
        num_webhooks = 100
        processing_times = []
        
        event = sample_webhook_events['payment_success']
        
        with patch('stripe.Webhook.construct_event', return_value=event):
            for _ in range(num_webhooks):
                start_time = time.time()
                response = client.post(
                    '/api/v1/webhooks/stripe',
                    json=event,
                    headers={'Stripe-Signature': 'test_signature'}
                )
                end_time = time.time()
                
                processing_times.append(end_time - start_time)
                assert response.status_code == 200
        
        avg_processing_time = statistics.mean(processing_times)
        p95_processing_time = statistics.quantiles(processing_times, n=20)[18]  # 95th percentile
        
        assert avg_processing_time < 0.1  # Average processing time < 100ms
        assert p95_processing_time < 0.2  # 95th percentile < 200ms

@pytest.mark.performance
class TestDatabasePerformance:
    def test_credit_operation_performance(self, credit_service, test_user):
        """Test performance of credit operations under load."""
        num_operations = 1000
        operation_times = []
        
        # Test credit additions
        start_time = time.time()
        for _ in range(num_operations):
            success, _ = credit_service.add_credits(test_user.id, 1.0)
            assert success
        end_time = time.time()
        
        total_time = end_time - start_time
        ops_per_second = num_operations / total_time
        
        assert ops_per_second > 100  # At least 100 operations per second

    def test_concurrent_db_operations(self, db_session, test_user):
        """Test database performance under concurrent operations."""
        num_threads = 10
        ops_per_thread = 100
        
        def perform_db_operations():
            for _ in range(ops_per_thread):
                # Simulate a typical transaction
                payment = Payment(
                    user_id=test_user.id,
                    amount=5.00,
                    currency="USD",
                    status="pending"
                )
                db_session.add(payment)
                db_session.commit()
                
                # Read operation
                db_session.query(Payment).filter_by(user_id=test_user.id).first()
        
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(perform_db_operations) for _ in range(num_threads)]
            concurrent.futures.wait(futures)
        end_time = time.time()
        
        total_operations = num_threads * ops_per_thread
        total_time = end_time - start_time
        ops_per_second = total_operations / total_time
        
        assert ops_per_second > 50  # At least 50 operations per second

@pytest.mark.performance
class TestResourceUsage:
    @pytest.mark.slow
    def test_memory_usage(self, client, test_user):
        """Test memory usage under load."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Generate load
        for _ in range(1000):
            client.get(
                '/api/v1/credits/balance',
                headers={'Authorization': f'Bearer {test_user.create_token()}'}
            )
        
        final_memory = process.memory_info().rss
        memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB
        
        assert memory_increase < 50  # Less than 50MB increase

    @pytest.mark.slow
    def test_connection_pool_efficiency(self, db_session):
        """Test database connection pool efficiency."""
        from sqlalchemy import create_engine
        from sqlalchemy.pool import QueuePool
        
        engine = create_engine(
            'postgresql://localhost/testdb',
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10
        )
        
        def make_db_query():
            with engine.connect() as conn:
                conn.execute("SELECT 1")
        
        # Test concurrent connections
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_db_query) for _ in range(100)]
            concurrent.futures.wait(futures)
        
        pool_status = engine.pool.status()
        assert pool_status.checkedin == pool_status.checkedout  # All connections returned
        assert pool_status.overflow <= 10  # Max overflow not exceeded 