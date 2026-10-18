-- Property Management schema (PostgreSQL)
-- Normalized: gl_account_dimension is the single source of GL names,
-- typed columns replace text-encoded values, constraints protect data quality,
-- and indexes cover the join / filter paths used by the reports below.

-- =====================================================================
-- Dimensions
-- =====================================================================
CREATE TABLE gl_account_dimension (
    gl_id       INT  PRIMARY KEY,
    gl_account  TEXT NOT NULL UNIQUE,
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

CREATE TABLE property_lease_data (
    property_id    INT PRIMARY KEY,
    community_name TEXT         NOT NULL,
    address        TEXT         NOT NULL,
    city           TEXT         NOT NULL,
    state          CHAR(2)      NOT NULL,
    units          INT          NOT NULL CHECK (units > 0),
    occupancy_rate NUMERIC(5,2) NOT NULL CHECK (occupancy_rate BETWEEN 0 AND 100) -- percent, e.g. 92.00
);

INSERT INTO property_lease_data VALUES
(101, 'Sunset Village', '123 Main St', 'Miami', 'FL', 150, 92),
(102, 'Green Meadows', '456 Oak Dr', 'Austin', 'TX', 200, 85),
(103, 'Sunrise MHP', '789 Smith St', 'Atlanta', 'GA', 68, 75),
(104, 'Pinewood Apts', '321 Elm St', 'Charlotte', 'NC', 120, 88),
(105, 'Lakeside MHP', '951 River Rd', 'Orlando', 'FL', 90, 80),
(106, 'Hilltop Homes', '147 Sunset Blvd', 'Denver', 'CO', 175, 95);

-- =====================================================================
-- Facts
-- =====================================================================
CREATE TABLE tenant_rent_payment_history (
    tenant_id         INT           PRIMARY KEY,
    property_id       INT           NOT NULL REFERENCES property_lease_data(property_id),
    lease_start       DATE          NOT NULL,
    lease_end         DATE          NOT NULL,
    monthly_rent      NUMERIC(10,2) NOT NULL CHECK (monthly_rent >= 0),
    last_payment_date DATE,
    payment_status    TEXT          NOT NULL
        CHECK (payment_status IN ('Paid', 'Overdue', 'Partial', 'Late Fee Added')),
    amount_paid       NUMERIC(10,2) CHECK (amount_paid >= 0), -- only filled for partial payments
    CHECK (lease_end > lease_start)
);

INSERT INTO tenant_rent_payment_history VALUES
(201, 101, '2023-06-01', '2024-06-01',  900, '2024-02-01', 'Paid',           NULL),
(202, 101, '2023-07-15', '2024-07-15',  875, '2024-01-15', 'Overdue',        NULL),
(203, 102, '2022-12-10', '2024-12-10', 1100, '2024-02-05', 'Paid',           NULL),
(204, 103, '2024-02-01', '2025-02-01',  950, '2024-02-20', 'Partial',        500),
(205, 104, '2023-09-20', '2024-09-20', 1200, '2024-03-01', 'Late Fee Added', NULL);

CREATE TABLE maintenance_work_orders (
    workorder_id    TEXT          PRIMARY KEY,
    property_id     INT           NOT NULL REFERENCES property_lease_data(property_id),
    request_date    DATE          NOT NULL,
    completion_date DATE,
    issue_type      TEXT          NOT NULL,
    cost            NUMERIC(10,2) NOT NULL CHECK (cost >= 0),
    status          TEXT          NOT NULL CHECK (status IN ('Pending', 'In Progress', 'Completed')),
    CHECK (completion_date IS NULL OR completion_date >= request_date),
    CHECK ((status = 'Completed') = (completion_date IS NOT NULL))
);

INSERT INTO maintenance_work_orders VALUES
('WO-001', 101, '2024-01-10', '2024-01-12', 'Plumbing Leak', 250, 'Completed'),
('WO-002', 102, '2024-02-05', NULL, 'Roof Repair', 1500, 'Pending'),
('WO-003', 103, '2024-02-15', '2024-02-18', 'HVAC Fix', 600, 'Completed'),
('WO-004', 104, '2024-01-25', NULL, 'Electrical', 750, 'In Progress'),
('WO-005', 105, '2024-02-20', NULL, 'Pest Control', 350, 'Pending');

-- gl_account name is no longer duplicated here; join gl_account_dimension.
CREATE TABLE budgeted_expenses (
    property_id     INT           NOT NULL REFERENCES property_lease_data(property_id),
    gl_id           INT           NOT NULL REFERENCES gl_account_dimension(gl_id),
    budget_date     DATE          NOT NULL,
    budgeted_amount NUMERIC(12,2) NOT NULL CHECK (budgeted_amount >= 0),
    PRIMARY KEY (property_id, gl_id, budget_date)
);

INSERT INTO budgeted_expenses (property_id, gl_id, budgeted_amount, budget_date) VALUES
(101, 501, 10000, '2024-01-01'),
(102, 502, 5000,  '2024-01-01'),
(103, 503, 3500,  '2024-01-01'),
(104, 504, 7200,  '2024-01-01'),
(105, 505, 1500,  '2024-01-01');

CREATE TABLE actual_expenses (
    expense_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    property_id   INT           NOT NULL REFERENCES property_lease_data(property_id),
    gl_id         INT           NOT NULL REFERENCES gl_account_dimension(gl_id),
    actual_amount NUMERIC(12,2) NOT NULL CHECK (actual_amount >= 0),
    expense_date  DATE          NOT NULL
);

INSERT INTO actual_expenses (property_id, gl_id, actual_amount, expense_date) VALUES
(101, 501, 9800, '2024-02-01'),
(101, 502, 1200, '2024-02-05'),
(102, 503, 3800, '2024-02-10'),
(102, 502, 5500, '2024-02-15'),
(103, 501, 2200, '2024-02-18'),
(103, 503, 3200, '2024-02-20'),
(105, 505, 1400, '2024-02-25');

-- =====================================================================
-- Indexes (FK columns are not indexed automatically in PostgreSQL)
-- =====================================================================
CREATE INDEX idx_rent_property          ON tenant_rent_payment_history (property_id);
CREATE INDEX idx_rent_status            ON tenant_rent_payment_history (payment_status);
CREATE INDEX idx_wo_property            ON maintenance_work_orders (property_id);
CREATE INDEX idx_wo_open                ON maintenance_work_orders (property_id) WHERE status <> 'Completed';
CREATE INDEX idx_budget_gl              ON budgeted_expenses (gl_id);
CREATE INDEX idx_actual_property_gl_dt  ON actual_expenses (property_id, gl_id, expense_date);
CREATE INDEX idx_actual_gl              ON actual_expenses (gl_id);

-- =====================================================================
-- Queries
-- =====================================================================

/* Task 6: Top 3 most profitable properties by rental income */
SELECT
    p.property_id,
    p.community_name,
    SUM(t.monthly_rent) AS total_rental_income
FROM tenant_rent_payment_history t
JOIN property_lease_data p ON p.property_id = t.property_id
GROUP BY p.property_id, p.community_name
ORDER BY total_rental_income DESC
LIMIT 3;

/* Highest expense by property and GL account */
SELECT
    a.property_id,
    p.community_name,
    g.gl_account,
    SUM(a.actual_amount) AS total_expense
FROM actual_expenses a
JOIN property_lease_data p ON p.property_id = a.property_id
JOIN gl_account_dimension g ON g.gl_id = a.gl_id
GROUP BY a.property_id, p.community_name, g.gl_account
ORDER BY total_expense DESC
LIMIT 1;
