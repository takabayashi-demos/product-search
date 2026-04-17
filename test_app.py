"""Tests for product-search service."""
import unittest
import json
from app import app

class TestProductSearch(unittest.TestCase):
    
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
    
    def test_health(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'UP')
    
    def test_search_basic(self):
        response = self.app.get('/api/v1/search?q=laptop')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertGreater(data['total'], 0)
        self.assertEqual(data['query'], 'laptop')
    
    def test_search_category_filter(self):
        response = self.app.get('/api/v1/search?q=e&category=electronics')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertGreater(data['total'], 0)
        for item in data['items']:
            self.assertEqual(item['category'], 'Electronics')
        self.assertIn('filters', data)
        self.assertEqual(data['filters']['category'], 'electronics')
    
    def test_search_sort_by_price_asc(self):
        response = self.app.get('/api/v1/search?q=e&sort_by=price&sort_order=asc')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        prices = [item['price'] for item in data['items']]
        self.assertEqual(prices, sorted(prices))
    
    def test_search_sort_by_price_desc(self):
        response = self.app.get('/api/v1/search?q=e&sort_by=price&sort_order=desc')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        prices = [item['price'] for item in data['items']]
        self.assertEqual(prices, sorted(prices, reverse=True))
    
    def test_search_sort_by_name(self):
        response = self.app.get('/api/v1/search?q=e&sort_by=name')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        names = [item['name'] for item in data['items']]
        self.assertEqual(names, sorted(names))
    
    def test_search_category_and_sort_combined(self):
        response = self.app.get('/api/v1/search?q=e&category=accessories&sort_by=price&sort_order=desc')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        for item in data['items']:
            self.assertEqual(item['category'], 'Accessories')
        prices = [item['price'] for item in data['items']]
        self.assertEqual(prices, sorted(prices, reverse=True))
    
    def test_search_missing_query(self):
        response = self.app.get('/api/v1/search')
        self.assertEqual(response.status_code, 400)
    
    def test_get_products(self):
        response = self.app.get('/api/v1/products')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertGreater(data['total'], 0)

if __name__ == '__main__':
    unittest.main()
