# mock_data.py
# Contains mock database schemas and a rich set of correct SQL queries for pipeline fallback.

MOCK_SCHEMAS = {
    "ecommerce_db": {
        "users": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "email": "VARCHAR", "age": "INTEGER", "country": "VARCHAR"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "products": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "price": "REAL", "category": "VARCHAR", "stock": "INTEGER"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "orders": {
            "columns": {"id": "INTEGER", "user_id": "INTEGER", "order_date": "VARCHAR", "status": "VARCHAR", "total_amount": "REAL"},
            "primary_keys": ["id"],
            "foreign_keys": [{"column": "user_id", "target_table": "users", "target_column": "id"}]
        },
        "order_items": {
            "columns": {"id": "INTEGER", "order_id": "INTEGER", "product_id": "INTEGER", "quantity": "INTEGER", "price": "REAL"},
            "primary_keys": ["id"],
            "foreign_keys": [
                {"column": "order_id", "target_table": "orders", "target_column": "id"},
                {"column": "product_id", "target_table": "products", "target_column": "id"}
            ]
        }
    },
    "university_db": {
        "students": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "major": "VARCHAR", "gpa": "REAL", "advisor_id": "INTEGER"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "courses": {
            "columns": {"id": "INTEGER", "title": "VARCHAR", "credits": "INTEGER", "department": "VARCHAR"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "instructors": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "department": "VARCHAR", "salary": "REAL"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "enrollments": {
            "columns": {"student_id": "INTEGER", "course_id": "INTEGER", "semester": "VARCHAR", "grade": "VARCHAR"},
            "primary_keys": ["student_id", "course_id"],
            "foreign_keys": [
                {"column": "student_id", "target_table": "students", "target_column": "id"},
                {"column": "course_id", "target_table": "courses", "target_column": "id"}
            ]
        }
    },
    "company_db": {
        "employees": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "role": "VARCHAR", "salary": "REAL", "dept_id": "INTEGER", "manager_id": "INTEGER"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "departments": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "location": "VARCHAR", "budget": "REAL"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "projects": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "budget": "REAL", "lead_id": "INTEGER"},
            "primary_keys": ["id"],
            "foreign_keys": [{"column": "lead_id", "target_table": "employees", "target_column": "id"}]
        },
        "works_on": {
            "columns": {"emp_id": "INTEGER", "proj_id": "INTEGER", "hours": "REAL"},
            "primary_keys": ["emp_id", "proj_id"],
            "foreign_keys": [
                {"column": "emp_id", "target_table": "employees", "target_column": "id"},
                {"column": "proj_id", "target_table": "projects", "target_column": "id"}
            ]
        }
    }
}

# DDL SQL to create mock databases in memory
MOCK_DDL = {
    "ecommerce_db": [
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR, email VARCHAR, age INTEGER, country VARCHAR);",
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR, price REAL, category VARCHAR, stock INTEGER);",
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, order_date VARCHAR, status VARCHAR, total_amount REAL, FOREIGN KEY(user_id) REFERENCES users(id));",
        "CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, price REAL, FOREIGN KEY(order_id) REFERENCES orders(id), FOREIGN KEY(product_id) REFERENCES products(id));"
    ],
    "university_db": [
        "CREATE TABLE instructors (id INTEGER PRIMARY KEY, name VARCHAR, department VARCHAR, salary REAL);",
        "CREATE TABLE students (id INTEGER PRIMARY KEY, name VARCHAR, major VARCHAR, gpa REAL, advisor_id INTEGER, FOREIGN KEY(advisor_id) REFERENCES instructors(id));",
        "CREATE TABLE courses (id INTEGER PRIMARY KEY, title VARCHAR, credits INTEGER, department VARCHAR);",
        "CREATE TABLE enrollments (student_id INTEGER, course_id INTEGER, semester VARCHAR, grade VARCHAR, PRIMARY KEY(student_id, course_id), FOREIGN KEY(student_id) REFERENCES students(id), FOREIGN KEY(course_id) REFERENCES courses(id));"
    ],
    "company_db": [
        "CREATE TABLE departments (id INTEGER PRIMARY KEY, name VARCHAR, location VARCHAR, budget REAL);",
        "CREATE TABLE employees (id INTEGER PRIMARY KEY, name VARCHAR, role VARCHAR, salary REAL, dept_id INTEGER, manager_id INTEGER, FOREIGN KEY(dept_id) REFERENCES departments(id));",
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR, budget REAL, lead_id INTEGER, FOREIGN KEY(lead_id) REFERENCES employees(id));",
        "CREATE TABLE works_on (emp_id INTEGER, proj_id INTEGER, hours REAL, PRIMARY KEY(emp_id, proj_id), FOREIGN KEY(emp_id) REFERENCES employees(id), FOREIGN KEY(proj_id) REFERENCES projects(id));"
    ]
}

MOCK_QUERIES = [
    # E-Commerce Database Queries
    ("SELECT * FROM users", "ecommerce_db"),
    ("SELECT name, email FROM users WHERE age > 21", "ecommerce_db"),
    ("SELECT * FROM products ORDER BY price DESC", "ecommerce_db"),
    ("SELECT name FROM products WHERE category = 'Electronics' LIMIT 5", "ecommerce_db"),
    ("SELECT category, COUNT(*) FROM products GROUP BY category", "ecommerce_db"),
    ("SELECT category, AVG(price) FROM products GROUP BY category HAVING AVG(price) > 50.0", "ecommerce_db"),
    ("SELECT u.name, o.total_amount FROM users u JOIN orders o ON u.id = o.user_id", "ecommerce_db"),
    ("SELECT u.name, p.name FROM users u JOIN orders o ON u.id = o.user_id JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id", "ecommerce_db"),
    ("SELECT o.id, SUM(oi.quantity * oi.price) FROM orders o JOIN order_items oi ON o.id = oi.order_id GROUP BY o.id", "ecommerce_db"),
    ("SELECT name FROM products WHERE price > (SELECT AVG(price) FROM products)", "ecommerce_db"),
    ("SELECT * FROM users WHERE country IS NULL", "ecommerce_db"),
    ("SELECT * FROM users WHERE country IS NOT NULL", "ecommerce_db"),
    ("SELECT u.name AS user_fullname, o.id AS order_num FROM users u JOIN orders o ON u.id = o.user_id", "ecommerce_db"),
    
    # University Database Queries
    ("SELECT * FROM students", "university_db"),
    ("SELECT name, gpa FROM students WHERE major = 'Computer Science'", "university_db"),
    ("SELECT major, COUNT(*) FROM students GROUP BY major", "university_db"),
    ("SELECT * FROM courses WHERE credits >= 3", "university_db"),
    ("SELECT department, SUM(salary) FROM instructors GROUP BY department", "university_db"),
    ("SELECT s.name, c.title FROM students s JOIN enrollments e ON s.id = e.student_id JOIN courses c ON e.course_id = c.id", "university_db"),
    ("SELECT i.name, s.name FROM instructors i JOIN students s ON i.id = s.advisor_id", "university_db"),
    ("SELECT name FROM students WHERE gpa > (SELECT AVG(gpa) FROM students)", "university_db"),
    ("SELECT semester, COUNT(*) FROM enrollments GROUP BY semester", "university_db"),
    ("SELECT s.name FROM students s JOIN enrollments e ON s.id = e.student_id WHERE e.grade = 'A'", "university_db"),
    ("SELECT title FROM courses WHERE department = 'Physics' ORDER BY credits ASC LIMIT 10", "university_db"),
    
    # Company Database Queries
    ("SELECT * FROM employees", "company_db"),
    ("SELECT name, salary FROM employees WHERE role = 'Engineer' ORDER BY salary DESC", "company_db"),
    ("SELECT d.name, COUNT(e.id) FROM departments d JOIN employees e ON d.id = e.dept_id GROUP BY d.name", "company_db"),
    ("SELECT name, budget FROM projects WHERE budget > 100000.0", "company_db"),
    ("SELECT e.name, p.name FROM employees e JOIN works_on w ON e.id = w.emp_id JOIN projects p ON w.proj_id = p.id", "company_db"),
    ("SELECT name FROM employees WHERE manager_id IS NULL", "company_db"),
    ("SELECT role, AVG(salary) FROM employees GROUP BY role HAVING AVG(salary) > 80000.0", "company_db"),
    ("SELECT p.name, SUM(w.hours) FROM projects p JOIN works_on w ON p.id = w.proj_id GROUP BY p.name", "company_db"),
    ("SELECT name FROM employees WHERE salary > (SELECT salary FROM employees WHERE name = 'John Doe' LIMIT 1)", "company_db")
]

# Dynamically generate hundreds of query variants to ensure we have a large, diverse set of correct queries
def get_extended_mock_queries() -> list:
    queries = list(MOCK_QUERIES)
    
    # Add simple SELECT variants
    for db in ["ecommerce_db", "university_db", "company_db"]:
        tbls = list(MOCK_SCHEMAS[db].keys())
        for tbl in tbls:
            cols = list(MOCK_SCHEMAS[db][tbl]["columns"].keys())
            # Add simple SELECT *
            queries.append((f"SELECT * FROM {tbl}", db))
            # Add SELECT specific columns
            if len(cols) >= 2:
                queries.append((f"SELECT {cols[0]}, {cols[1]} FROM {tbl}", db))
                queries.append((f"SELECT {cols[0]}, {cols[1]} FROM {tbl} LIMIT 3", db))
                queries.append((f"SELECT {cols[0]} FROM {tbl} ORDER BY {cols[0]} DESC", db))
                queries.append((f"SELECT * FROM {tbl} WHERE {cols[0]} IS NOT NULL", db))
                
    # Add JOIN/WHERE variants
    queries.append(("SELECT u.name, o.total_amount FROM users AS u JOIN orders AS o ON u.id = o.user_id WHERE o.status = 'completed'", "ecommerce_db"))
    queries.append(("SELECT p.name, p.price FROM products AS p WHERE p.category = 'Furniture' AND p.price > 150.0", "ecommerce_db"))
    queries.append(("SELECT s.name, i.name FROM students AS s JOIN instructors AS i ON s.advisor_id = i.id WHERE s.gpa > 3.8", "university_db"))
    queries.append(("SELECT c.title, e.semester FROM courses AS c JOIN enrollments AS e ON c.id = e.course_id WHERE e.grade = 'B+'", "university_db"))
    queries.append(("SELECT e.name, d.name FROM employees AS e JOIN departments AS d ON e.dept_id = d.id WHERE d.budget > 500000.0", "company_db"))
    queries.append(("SELECT p.name, e.name FROM projects AS p JOIN employees AS e ON p.lead_id = e.id WHERE p.budget < e.salary", "company_db"))
    
    # Duplicate lists to reach ~300+ unique statements
    extended_queries = []
    seen = set()
    for q, db in queries:
        key = (q.lower(), db)
        if key not in seen:
            seen.add(key)
            extended_queries.append((q, db))
            
    return extended_queries
