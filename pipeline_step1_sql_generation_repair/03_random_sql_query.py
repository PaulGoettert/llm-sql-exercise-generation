import random

EXAMPLES_BY_DIFFICULTY = {
    "1": [
        "SELECT title FROM books WHERE published_year > 2015;",
        "SELECT customer_name FROM customers WHERE country = 'Canada' AND status = 'active';",
        "SELECT product_id, price FROM products WHERE price BETWEEN 10 AND 25;",
        "SELECT athlete FROM marathon WHERE finish_time < 240;",
        "SELECT movie_title FROM movies WHERE rating >= 8.5;"
    ],
    "2": [
        "SELECT o.order_id, c.customer_name FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.city = 'Paris';",
        "SELECT s.student_name, cl.class_name FROM students s JOIN classes cl ON s.class_id = cl.id WHERE cl.term = 'Fall';",
        "SELECT a.album_title, ar.artist_name FROM album a JOIN artist ar ON a.artist_id = ar.id WHERE ar.country = 'Brazil';",
        "SELECT inv.invoice_id, emp.name FROM invoices inv JOIN employees emp ON inv.sales_rep_id = emp.id;",
        "SELECT p.project_name, d.department_name FROM project p JOIN department d ON p.department_id = d.id WHERE d.region = 'APAC';"
    ],
    "3": [
        "SELECT supplier_name FROM suppliers s WHERE NOT EXISTS (SELECT 1 FROM shipments sh WHERE sh.supplier_id = s.id);",
        "SELECT course_id FROM courses WHERE course_id NOT IN (SELECT course_id FROM enrollments);",
        "SELECT employee_id FROM employees e WHERE NOT EXISTS (SELECT 1 FROM bonus b WHERE b.employee_id = e.id);",
        "SELECT venue FROM events WHERE venue NOT IN (SELECT venue FROM bookings);",
        "SELECT product_code FROM catalog WHERE product_code NOT IN (SELECT product_code FROM warehouse_stock);"
    ],
    "4": [
        "SELECT AVG(balance) FROM accounts WHERE branch = 'Downtown';",
        "SELECT COUNT(*) FROM tickets WHERE status = 'open';",
        "SELECT SUM(amount) FROM donations WHERE campaign = 'Clean Water';",
        "SELECT MIN(delivery_time) FROM shipments WHERE carrier = 'FastTrack';",
        "SELECT MAX(score) FROM exams WHERE subject = 'Mathematics';"
    ],
    "5": [
        "SELECT department_id, AVG(salary) AS avg_salary FROM employees GROUP BY department_id;",
        "SELECT genre, COUNT(*) AS movie_count FROM movies GROUP BY genre;",
        "SELECT store_id, SUM(total) AS revenue FROM sales GROUP BY store_id;",
        "SELECT region, AVG(score) FROM surveys GROUP BY region;",
        "SELECT coach_id, MAX(budget) FROM teams GROUP BY coach_id;"
    ],
    "6": [
        "SELECT department_id, COUNT(*) AS headcount FROM employees GROUP BY department_id HAVING COUNT(*) > 20;",
        "SELECT customer_id, SUM(total) AS total_spent FROM orders GROUP BY customer_id HAVING SUM(total) > 5000;",
        "SELECT product_category, AVG(price) FROM products GROUP BY product_category HAVING AVG(price) BETWEEN 50 AND 200;",
        "SELECT instructor_id, COUNT(*) FROM classes GROUP BY instructor_id HAVING COUNT(*) >= 3;",
        "SELECT supplier_id, MAX(delivery_days) FROM shipments GROUP BY supplier_id HAVING MAX(delivery_days) > 7;"
    ],
    "7": [
        "SELECT artist_name FROM artists UNION SELECT artist_name FROM retired_artists;",
        "SELECT city FROM airports UNION SELECT city FROM seaports;",
        "SELECT customer_name FROM customers LEFT JOIN vip ON customers.id = vip.customer_id UNION SELECT guest_name FROM guestbook;",
        "SELECT model FROM car_inventory UNION SELECT model FROM vintage_cars;",
        "SELECT team_name FROM league_a UNION SELECT team_name FROM league_b;"
    ],
    "8": [
        "SELECT d.department_name, COUNT(e.employee_id) AS staff_count FROM department d LEFT JOIN employee e ON d.id = e.department_id GROUP BY d.department_name;",
        "SELECT c.category_name, SUM(o.quantity) AS total_sold FROM category c LEFT JOIN order_items o ON c.id = o.category_id GROUP BY c.category_name;",
        "SELECT s.store_name, COALESCE(SUM(p.total), 0) AS sales FROM store s LEFT JOIN purchase p ON s.id = p.store_id GROUP BY s.store_name;",
        "SELECT r.route_name, COUNT(t.ticket_id) AS tickets FROM route r LEFT JOIN ticket t ON r.id = t.route_id GROUP BY r.route_name;",
        "SELECT u.university_name, COUNT(st.student_id) AS enrollment FROM university u LEFT JOIN student st ON u.id = st.university_id GROUP BY u.university_name;"
    ]
}


def get_handcrafted_examples(difficulty_level: str, k: int = 3):
    """
    Returns up to k diverse handcrafted example queries for the given difficulty level.
    """
    pool = EXAMPLES_BY_DIFFICULTY.get(str(difficulty_level), ["SELECT 1;"])
    if len(pool) >= k:
        return random.sample(pool, k)
    samples = pool[:]
    while len(samples) < k:
        samples.append(random.choice(pool))
    return samples
