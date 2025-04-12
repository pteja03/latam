-- Creating dimensions and inserting records
CREATE TABLE property_lease_data (
    property_id INT PRIMARY KEY,
    community_name TEXT,
    address TEXT,
    city TEXT,
    state CHAR(2),
    units INT,
    occupancy_rate CHAR(3) 
);

INSERT INTO property_lease_data VALUES
(101, 'Sunset Village', '123 Main St', 'Miami', 'FL', 150, '92%'),
(102, 'Green Meadows', '456 Oak Dr', 'Austin', 'TX', 200, '85%'),
(103, 'Sunrise MHP', '789 Smith St', 'Atlanta', 'GA', 68, '75%'),
(104, 'Pinewood Apts', '321 Elm St', 'Charlotte', 'NC', 120, '88%'),
(105, 'Lakeside MHP', '951 River Rd', 'Orlando', 'FL', 90, '80%'),
(106, 'Hilltop Homes', '147 Sunset Blvd', 'Denver', 'CO', 175, '95%');


CREATE TABLE tenant_rent_payment_history (
    tenant_id INT PRIMARY KEY,
    property_id INT REFERENCES property_lease_data(property_id),
    lease_start DATE,
    lease_end DATE,
    monthly_rent NUMERIC(10,2),
    last_payment_date DATE,
    payment_status TEXT
);

INSERT INTO tenant_rent_payment_history VALUES
(201, 101, '2023-06-01', '2024-06-01', 900, '2024-02-01', 'Paid'),
(202, 101, '2023-07-15', '2024-07-15', 875, '2024-01-15', 'Overdue'),
(203, 102, '2022-12-10', '2024-12-10', 1100, '2024-02-05', 'Paid'),
(204, 103, '2024-02-01', '2025-02-01', 950, '2024-02-20', 'Partial ($500)'),
(205, 104, '2023-09-20', '2024-09-20', 1200, '2024-03-01', 'Late Fee Added');


CREATE TABLE maintenance_work_orders (
    workorder_id TEXT PRIMARY KEY,
    property_id INT REFERENCES property_lease_data(property_id),
    request_date DATE,
    completion_date DATE,
    issue_type TEXT,
    cost NUMERIC(10,2),
    status TEXT
);

INSERT INTO maintenance_work_orders VALUES
('WO-001', 101, '2024-01-10', '2024-01-12', 'Plumbing Leak', 250, 'Completed'),
('WO-002', 102, '2024-02-05', NULL, 'Roof Repair', 1500, 'Pending'),
('WO-003', 103, '2024-02-15', '2024-02-18', 'HVAC Fix', 600, 'Completed'),
('WO-004', 104, '2024-01-25', NULL, 'Electrical', 750, 'In Progress'),
('WO-005', 105, '2024-02-20', NULL, 'Pest Control', 350, 'Pending');


CREATE TABLE budgeted_expenses (
    property_id INT REFERENCES property_lease_data(property_id),
    gl_id INT,
    gl_account TEXT,
    budgeted_amount NUMERIC(12,2),
    budget_date DATE
);

INSERT INTO budgeted_expenses VALUES
(101, 501, 'Repairs & Maint', 10000, '2024-01-01'),
(102, 502, 'Utilities', 5000, '2024-01-01'),
(103, 503, 'Landscaping', 3500, '2024-01-01'),
(104, 504, 'Insurance', 7200, '2024-01-01'),
(105, 505, 'Pest Control', 1500, '2024-01-01');


CREATE TABLE actual_expenses (
    property_id INT REFERENCES property_lease_data(property_id),
    gl_id INT,
    gl_account TEXT,
    actual_amount NUMERIC(12,2),
    expense_date DATE
);

INSERT INTO actual_expenses VALUES
(101, 501, 'Repairs & Maint', 9800, '2024-02-01'),
(101, 502, 'Utilities', 1200, '2024-02-05'),
(102, 503, 'Landscaping', 3800, '2024-02-10'),
(102, 502, 'Utilities', 5500, '2024-02-15'),
(103, 501, 'Repairs & Maint', 2200, '2024-02-18'),
(103, 503, 'Landscaping', 3200, '2024-02-20'),
(105, 505, 'Pest Control', 1400, '2024-02-25');


CREATE TABLE gl_account_dimension (
    gl_id INT PRIMARY KEY,
    gl_account TEXT,
    description TEXT
);

INSERT INTO gl_account_dimension VALUES
(501, 'Repairs & Maint', 'Costs for property repairs'),
(502, 'Utilities', 'Electricity, water, gas'),
(503, 'Landscaping', 'Lawn care and upkeep'),
(504, 'Insurance', 'Property insurance premiums'),
(505, 'Pest Control', 'Extermination services'),
(506, 'Security', 'On-site security services'),
(507, 'Legal Fees', 'Attorney and legal costs'),
(508, 'Marketing', 'Advertising and promotions');

/*Task 6: Identify the Top 3 Most Profitable Properties by Rental income
 Write a SQL query to return the top 3 properties by total rental income:*/

SELECT 
    p.property_id,
    p.community_name,
    SUM(t.monthly_rent) AS total_rental_income
FROM 
    tenant_rent_payment_history t
JOIN 
    property_lease_data p ON t.property_id = p.property_id
GROUP BY 
    p.property_id, p.community_name
ORDER BY 
    total_rental_income DESC
LIMIT 3;
 

SELECT 
    a.property_id,
    p.community_name,
    a.gl_account,
    SUM(a.actual_amount) AS total_expense
FROM 
    actual_expenses a
JOIN 
    property_lease_data p ON a.property_id = p.property_id
GROUP BY 
    a.property_id, p.community_name, a.gl_account
ORDER BY 
    total_expense DESC
LIMIT 1;



