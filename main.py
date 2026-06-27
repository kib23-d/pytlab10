import psycopg2
from faker import Faker
import random
from tabulate import tabulate
import pandas as pd

# Підключення до БД PostgreSQL
conn = psycopg2.connect(
    dbname="shop_db",
    user="admin",
    password="password",
    host="localhost",
    port="5432"
)
cursor = conn.cursor()
fake = Faker('uk_UA')

def setup_database():
    # Видалення існуючих таблиць для чистого запуску
    cursor.execute("DROP TABLE IF EXISTS sales, products, clients CASCADE;")
    
    # 1. Таблиця Клієнти
    cursor.execute("""
        CREATE TABLE clients (
            client_id SERIAL PRIMARY KEY,
            company_name VARCHAR(255) NOT NULL,
            entity_type VARCHAR(50) CHECK (entity_type IN ('юридична', 'фізична')),
            address TEXT,
            phone VARCHAR(20),
            contact_person VARCHAR(100),
            checking_account VARCHAR(50)
        );
    """)

    # 2. Таблиця Товари
    cursor.execute("""
        CREATE TABLE products (
            product_id SERIAL PRIMARY KEY,
            product_name VARCHAR(255) NOT NULL,
            price NUMERIC(10, 2) NOT NULL,
            stock_quantity INT NOT NULL
        );
    """)

    # 3. Таблиця Продаж товарів
    cursor.execute("""
        CREATE TABLE sales (
            sale_id SERIAL PRIMARY KEY,
            sale_date DATE NOT NULL,
            client_id INT REFERENCES clients(client_id),
            product_id INT REFERENCES products(product_id),
            quantity INT NOT NULL,
            discount INT CHECK (discount >= 3 AND discount <= 20),
            payment_method VARCHAR(50) CHECK (payment_method IN ('готівковий', 'безготівковий')),
            delivery_needed BOOLEAN,
            delivery_cost NUMERIC(10, 2)
        );
    """)

    # Заповнення даними (4 клієнта, 10 товарів, 19 продажів)
    entity_types = ['юридична', 'фізична']
    payment_methods = ['готівковий', 'безготівковий']

    # Генерація клієнтів
    for _ in range(4):
        cursor.execute(
            "INSERT INTO clients (company_name, entity_type, address, phone, contact_person, checking_account) VALUES (%s, %s, %s, %s, %s, %s)",
            (fake.company(), random.choice(entity_types), fake.address(), fake.phone_number(), fake.name(), fake.iban())
        )

    # Генерація товарів
    products_list = ["Ноутбук", "Смартфон", "Планшет", "Монітор", "Клавіатура", "Мишка", "Принтер", "Навушники", "Вебкамера", "Роутер"]
    for product in products_list:
        cursor.execute(
            "INSERT INTO products (product_name, price, stock_quantity) VALUES (%s, %s, %s)",
            (product, round(random.uniform(500, 35000), 2), random.randint(10, 100))
        )

    # Генерація продажів (19)
    for _ in range(19):
        del_needed = fake.boolean()
        cursor.execute(
            "INSERT INTO sales (sale_date, client_id, product_id, quantity, discount, payment_method, delivery_needed, delivery_cost) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                fake.date_between(start_date='-1y', end_date='today'),
                random.randint(1, 4),
                random.randint(1, 10),
                random.randint(1, 5),
                random.randint(3, 20),
                random.choice(payment_methods),
                del_needed,
                round(random.uniform(50, 500), 2) if del_needed else 0
            )
        )
    conn.commit()

def run_query(query, title, params=None):
    print(f"\n{'='*80}\n{title}\n{'-'*80}")
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    
    col_names = [desc[0] for desc in cursor.description]
    data = cursor.fetchall()
    print(tabulate(data, headers=col_names, tablefmt="psql"))

def execute_queries():
    # 1. Продажі, оплачені готівкою (сортування по клієнту)
    run_query("""
        SELECT s.sale_id, c.company_name, s.sale_date, s.payment_method 
        FROM sales s 
        JOIN clients c ON s.client_id = c.client_id 
        WHERE s.payment_method = 'готівковий' 
        ORDER BY c.company_name;
    """, "1. Продажі готівкою (сортування за клієнтом)")

    # 2. Продажі з доставкою
    run_query("""
        SELECT * FROM sales WHERE delivery_needed = TRUE;
    """, "2. Продажі по яких потрібна доставка")

    # 3. Сума до сплати (з урахуванням знижки та без неї)
    run_query("""
        SELECT c.company_name, 
               SUM(s.quantity * p.price + s.delivery_cost) as total_without_discount,
               SUM(s.quantity * p.price * (100 - s.discount) / 100.0 + s.delivery_cost) as total_with_discount
        FROM sales s
        JOIN clients c ON s.client_id = c.client_id
        JOIN products p ON s.product_id = p.product_id
        GROUP BY c.company_name;
    """, "3. Сума до сплати (з/без знижки) кожному клієнту")

    # 4. Всі покупки вказаного клієнта (Параметр)
    cursor.execute("SELECT company_name FROM clients LIMIT 1;")
    target_client = cursor.fetchone()[0]
    run_query("""
        SELECT s.sale_id, p.product_name, s.quantity, s.sale_date 
        FROM sales s
        JOIN clients c ON s.client_id = c.client_id
        JOIN products p ON s.product_id = p.product_id
        WHERE c.company_name = %s;
    """, f"4. Всі покупки клієнта: {target_client}", (target_client,))

    # 5. Кількість покупок кожного клієнта
    run_query("""
        SELECT c.company_name, COUNT(s.sale_id) as purchases_count
        FROM clients c
        LEFT JOIN sales s ON c.client_id = s.client_id
        GROUP BY c.company_name;
    """, "5. Кількість покупок (підсумковий запит)")

    # 6. Сума за готівкою та безготівкою (перехресний запит / crosstab)
    run_query("""
        SELECT c.company_name,
               SUM(CASE WHEN s.payment_method = 'готівковий' THEN s.quantity * p.price * (100 - s.discount) / 100.0 ELSE 0 END) as cash_sum,
               SUM(CASE WHEN s.payment_method = 'безготівковий' THEN s.quantity * p.price * (100 - s.discount) / 100.0 ELSE 0 END) as cashless_sum
        FROM clients c
        LEFT JOIN sales s ON c.client_id = s.client_id
        LEFT JOIN products p ON s.product_id = p.product_id
        GROUP BY c.company_name;
    """, "6. Перехресний запит (Готівка vs Безготівка)")

if __name__ == "__main__":
    setup_database()
    print("БД успішно ініціалізована даними.")
    execute_queries()
    
    cursor.close()
    conn.close()