import time
import functools
from django.db import connection
import logging

logger = logging.getLogger(__name__)

def track_performance(func):
    """
    Decorator to track the execution time and database query count of a function.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        initial_queries = len(connection.queries)
        start_time = time.time()
        
        result = func(*args, **kwargs)
        
        end_time = time.time()
        final_queries = len(connection.queries)
        
        execution_time = end_time - start_time
        queries_made = final_queries - initial_queries
        
        print(f"[Performance Tracking] {func.__name__} | Time: {execution_time:.4f}s | Queries: {queries_made}")
        logger.info(f"{func.__name__} executed in {execution_time:.4f}s with {queries_made} queries.")
        
        return result
    return wrapper

class PerformanceTrackingMiddleware:
    """
    Middleware to track API/View endpoints performance.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        initial_queries = len(connection.queries)
        start_time = time.time()
        
        response = self.get_response(request)
        
        end_time = time.time()
        final_queries = len(connection.queries)
        
        execution_time = end_time - start_time
        queries_made = final_queries - initial_queries
        
        # يمكنك إضافة هذا في Log بدل الطباعة في حالة الإنتاج
        print(f"[API Endpoint] {request.method} {request.path} | Time: {execution_time:.4f}s | Queries: {queries_made}")
        
        return response
