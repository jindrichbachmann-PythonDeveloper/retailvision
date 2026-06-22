# RetailVision

AI-powered retail product recognition and catalog management platform.

RetailVision processes product photos, validates results, generates catalog records, manages inventory, and supports online sales workflows.

---

# Features

## Product Processing

* Multi-image upload
* Product detection
* Automatic object separation
* Smart cropping
* Background removal
* Image enhancement
* AI quality evaluation

## Product Verification

* Duplicate detection
* Possible duplicate detection
* Visual similarity analysis
* AI identity verification
* Validation before product approval

## Product Management

* Product catalog generation
* Inventory management
* Product approval workflow
* Product administration
* Product status management

## Customer Management

* User registration
* User login
* JWT authentication
* Email verification
* Customer records

## E-commerce

* Shopping cart
* Stripe payments
* Order management
* Order confirmation
* Invoice generation
* Invoice email delivery

---

# Technology Stack

## Python

Main application language used for backend logic, image processing, AI integration, database operations, invoice generation, and API implementation.

## FastAPI

Provides the REST API layer for authentication, image analysis, product management, orders, invoices, customers, payments, and frontend communication.

## OpenCV

Used for image preprocessing, enhancement, cropping, geometric checks, visual analysis, and computer vision operations.

## YOLOv8

Used for object detection and locating watches or products inside uploaded images before the splitting and validation pipeline.

## OpenAI API

Used for AI-assisted quality evaluation, product recognition, metadata generation, and validation workflows.

## MongoDB

Used as temporary and flexible storage during the image-processing pipeline.

MongoDB stores image-related processing data, intermediate product records, and flexible analysis results before final approval.

## GridFS

Used for storing image files inside MongoDB during the processing workflow.

## PostgreSQL

Used as the main structured database for confirmed business data.

Approved products, user-visible catalog records, orders, customers, invoices, and other relational business data are stored in PostgreSQL.

## Stripe

Used for checkout, payment processing, payment confirmation, and transaction handling.

## JWT Authentication

Used to secure user sessions and protected API endpoints.

## Cloudflare Tunnel

Used to expose the local FastAPI application to the public internet during development and testing without traditional port forwarding.

## HTML, CSS and JavaScript

Used for the administration interface, customer storefront, upload workflow, shopping cart, and order management pages.

## Email Workflows

Used for email verification, invoice delivery, order confirmation, and customer communication.

---

# Data Flow

1. User uploads product photos.
2. Images are processed through the computer vision pipeline.
3. Detected products are separated into individual candidates.
4. Candidate data and image files are stored in MongoDB / GridFS during processing.
5. AI quality checks and duplicate detection are applied.
6. Only approved products are written into PostgreSQL as user-visible catalog records.
7. Products can be published for sale.
8. Customers place orders through the shopping cart.
9. Stripe handles payment.
10. Orders, confirmations, and invoices are stored as structured business data.
11. Invoice and confirmation emails are sent to the customer.

---

# Architecture

```text
app/
├── api/
│   ├── auth
│   ├── analyze
│   ├── products
│   ├── customers
│   ├── orders
│   ├── invoices
│   ├── images
│   └── stripe
│
├── services/
│   ├── ai_cleanup_service
│   ├── ai_filter_debug
│   ├── ai_same_watch_guard
│   ├── analyze_service
│   ├── duplicate_service
│   ├── image_service
│   ├── split_service
│   ├── stripe_service
│   ├── invoice_service
│   ├── mongo_service
│   ├── gridfs_service
│   └── pg_service
│
├── web/
├── middleware/
├── core/
├── models/
└── db/
```

---

# Workflow

1. Upload product photos.
2. Detect products using YOLO.
3. Split products into individual candidates.
4. Perform image processing and validation.
5. Store temporary processing results in MongoDB / GridFS.
6. Run AI quality evaluation.
7. Run duplicate detection.
8. Approve valid products.
9. Save approved user-visible products into PostgreSQL.
10. Publish products for sale.
11. Process orders and payments.
12. Generate invoices and customer notifications.

---

# Installation

```bash
pip install -r requirements.txt
```

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

# Status

Current implementation includes:

* FastAPI backend
* YOLO object detection
* AI-assisted image processing
* MongoDB / GridFS processing storage
* PostgreSQL catalog and business data storage
* Duplicate detection
* Product approval workflow
* Product catalog management
* Customer management
* Stripe integration
* Invoice generation
* Email workflows
* Inventory management
