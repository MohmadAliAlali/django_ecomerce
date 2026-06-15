from locust import HttpUser, task, between
import random

class ProductShopper(HttpUser):
    # Simulate realistic human thinking time between clicks (1 to 4 seconds)
    wait_time = between(1, 4)

    @task(4)
    def browse_catalog(self):
        """Simulates a user scrolling through the main product list."""
        # Note: Adjust the URL path if your friends used a different routing scheme
        self.client.get("/api/products/")

    @task(2)
    def view_single_product(self):
        """Simulates a user clicking on a specific product."""
        # Assuming you have seeded the database with at least 50 products
        product_id = random.randint(1, 50)
        self.client.get(f"/api/products/{product_id}/")

    @task(1)
    def search_products(self):
        """Simulates a user searching for an item (heavy DB load)."""
        # Searches often bypass caches and force full database scans
        search_terms = ["laptop", "phone", "headset", "keyboard"]
        query = random.choice(search_terms)
        self.client.get(f"/api/products/?search={query}")