
# Backend Engineer Candidate Test: Python & Django (SOURCE OF TRUTH)
 
> Faithful translation of `Django-Candidate.pdf` ("Backend • Backend Engineering, Candidate Sheet").
> The PDF text layer was garbled (right-to-left), so this was read from the page images.
> Anything uncertain is marked **⚠ Interpretation** and listed at the bottom. Nothing here is invented: if it is not in this file, it was not in the PDF.
> Progress checkboxes live in `PLAN.md`. This file is only the requirements.
 
---
 
## Overview table (page 1)
 
| # | Task | Skill | Level | Hours (estimated) |
|---|------|-------|-------|-------------------|
| 1 | Merging payment event streams | Generator & algorithm | Mid-Senior | 3 |
| 2 | Venue reservation pricing engine | OOP & SOLID | Mid | 3 |
| 3 | Financial report per court | ORM & PostgreSQL | Mid-Senior | 5 |
| 4 | Goods transfer request cycle | DRF & API design | Mid-Senior | 5 |
| 5 | Reserving the last class seat | Transaction & concurrency | Senior | 4 |
| 6 | Branch invoice access | JWT & Authorization | Senior | 5 |
| 7 | Debtors report rebuild | Debugging & Refactoring | Mid-Senior | 4 |
| 8 | Recoverable receipt dispatch | Celery & Redis | Senior | 5 |
| 9 | Reservation cancellation policy test | pytest & Quality Engineering | Mid | 3 |
| 10 | Multi-branch ERP architecture | System Design & operations | Senior | 4 |
| | **Total** | | | **41** |
 
## Delivery conditions (page 1)
 
1. Each task is **independent**.
2. For each task, deliver **one folder** containing that sheet's outputs **and a README**.
3. In the README write: **run command, test command, assumptions, and unfinished parts**.
4. Times are estimates.
5. Target environment: **Python 3.12+**, and for DRF-related tasks **Django 5.x, DRF and PostgreSQL**.
6. **Specify dependency versions** (pin them).
7. Data must be **seed-built** and **setup must not depend on an external account**.
---
 
## Task 1: Merging payment event streams
*Generator & algorithm · Mid-Senior · 3 h*
 
**Scenario & mission**
Branch terminals produce files of events, each sorted by (UTC time, id). Write `merge(streams)` that takes up to **64** single-use **Iterators** and delivers a **sorted output gradually (lazily)**. Each event contains time, id, and an integer amount.
 
**Expected behavior**
- Copies of one event have the same time and id. A repeat with the same amount is output **once**.
- A different amount for the same key → **a clear error before that key is published**.
- Empty input and equal times work correctly.
**Sample / acceptance**
- First stream `[(1,A,7),(3,C,4)]` and second `[(1,A,7),(2,B,5)]` → must output in order **A, B, C**. ⚠
- Changing A's amount in the second stream to **8** → must raise an error. ⚠
**Constraints & deliverables**
- **Standard Library only.**
- **Memory must be a function of the number of streams** (not of the data size).
- Test with an **infinite Iterator** using limited consumption.
- Deliver: **memory measurement** and **Time/Space Complexity analysis**.
---
 
## Task 2: Venue reservation pricing engine
*OOP & SOLID · Mid · 3 h*
 
**Scenario & mission**
A reservation can have, at the same time, a court rate, a start-hour multiplier, and a membership discount. Design the `quote` engine so a **new policy can be added from outside** to the composition of policies.
 
**Expected behavior**
- Base amount is **first multiplied by the hour multiplier**, then **percentage discount**, and at the end the **fixed credit** is applied.
- Amount must **not be negative**.
- Rounding **HALF_UP to rial, only at the end**.
- Output: **final amount and the breakdown of each policy's effect**.
**Sample / acceptance**
- Base **1000**, multiplier **1.5**, discount **10%**, credit **200** → **1150**.
- Credit **2000** → result is **zero**.
- Re-running on the same input must give the **same result**.
**Constraints & deliverables**
- **Do not use `float`.**
- Add **a 4th policy of your own choice**.
- Deliver: **code, class diagram, shared contract test, and an explanation of the roles of Polymorphism, Encapsulation, Abstraction and Composition.**
---
 
## Task 3: Financial report per court
*ORM & PostgreSQL · Mid-Senior · 5 h*
 
**Scenario & mission**
Build the models **Payment, Booking, Court, Branch, Tag**. Each booking belongs to **one court** and has **multiple payments and multiple tags**. The admin page, for each court, wants: **the count of confirmed bookings, the sum of collected amounts, and the names of distinct tags**.
 
**Expected behavior**
- Date filter is on **booking start date**, as `[from, to]`.
- **A court with no bookings must also be displayed.**
- First build the **naive version** (iterate courts, read payments and tags per booking), **measure the Query count**, then provide an **optimized version**.
**Sample / acceptance**
- One confirmed booking with **two successful payments of 100 rial**, **one failed payment of 30 rial**, and **three tags** → count **1**, collected **200**. ⚠
- An empty court → count and amount **zero**.
**Constraints & deliverables**
- **At most 5 Queries for a page of 50 courts.**
- Include: **FK, Migration, Constraint, pagination, ManyToMany**.
- **Positive amount constraint**, **suggested Index**, **seed for 100,000 bookings**, **Query-count test**, and **EXPLAIN ANALYZE comparison**.
---
 
## Task 4: Goods transfer request cycle
*DRF & API design · Mid-Senior · 5 h*
 
**Scenario & mission**
The destination branch requests goods from the **source branch's warehouse**. Build the API: **list, detail, create, send for approval, and decision by the source manager**. This task covers **only the request cycle**.
 
**Expected behavior**
- Destination employee creates a **draft** and **sends** it.
- After sending, the source manager can **approve**, or **reject with a reason**.
- **The creator has no right to decide.**
- Employee sees **only requests of their own destination**; source manager sees **only submitted requests related to their own source**.
**Sample / acceptance**
- Request of **3 balls** from A to B is initially `draft`. Send → then approve → `approved`.
- **Second decision → 409.**
- **Quantity zero, or source equal to destination → 400.**
- **Detail outside visibility → 404.**
- **Forbidden action on a visible record → 403.**
**Constraints & deliverables**
- **Serializer, Permission, Authentication**, and **ViewSet or APIView** are required.
- Deliver: **filter, status, pagination with stable ordering, server-side recording of the decision-maker, and a role-matrix test.**
- **Direct change of `status` from the payload is not allowed.**
---
 
## Task 5: Reserving the last class seat
*Transaction & concurrency · Senior · 4 h*
 
**Scenario & mission**
For a class with **fixed capacity**, implement the operation `reserve(class_id, user_id, key)`. A user has **at most one reservation per class**. The request key is **unique within the user's scope**.
 
**Expected behavior**
- A repeated successful request **returns the same id**.
- Using the same successful key for **another class → 409**.
- Full capacity, **or** a repeat reservation with a **new key** → **409**.
- **A failure mid-operation must not consume capacity.**
**Sample / acceptance**
- Capacity **3** and **20 users simultaneously** → exactly **3 successes and 17 conflicts**.
- Two simultaneous requests with **one key and one user** for the last free seat must receive **one shared id**.
**Constraints & deliverables**
- **Real PostgreSQL** and an **independent connection per Worker** are required.
- Deliver: **Constraint, Migration, test with a shared start point (barrier), rollback test, and an explanation of Lock order.**
- **A lock in process memory is not acceptable.**
---
 
## Task 6: Branch invoice access
*JWT & Authorization · Senior · 5 h*
 
**Scenario & mission**
A financial analyst reads the invoices of one or more branches. A customer sees **only their own invoice**. The code below is the **initial version**: review it and complete the reading API.
 
**Initial code to review**
```python
class InvoiceViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer
 
    def get_queryset(self):
        if self.action == "list":
            return visible_invoices(self.request.user)
        return Invoice.objects.all()
```
 
**Expected behavior**
- Build **Login, refresh, and logout.**
- **Access token valid 5 minutes; Refresh valid 7 days.**
- **Refresh is rotated after use.**
- **Logout closes that same session.**
- **Removal of branch membership must take effect from the next request.**
**Sample / acceptance**
- Analyst is a member of A and B. After A's membership is removed, they see **only B** in the list.
- A record **outside the scope → 404**.
- **Expired token → 401**.
- **6th failed login attempt on one account within a 60-second window → 429.**
**Constraints & deliverables**
- **Use a JWT library.**
- **Do not log the key or the token.**
- Deliver: **permission test for list and detail, separation of two sessions, Rate Limiting shared between Workers, and a note on fixing the IDOR risk.**
---
 
## Task 7: Debtors report rebuild
*Debugging & Refactoring · Mid-Senior · 4 h*
 
**Scenario & mission**
The function below is used for the cash-desk report. **Record the correct contract with tests**, prioritize the defects, and replace the implementation. `Invoice` has correct `total`, `branch`, and `status`. `Payment` has correct `amount` and `status`.
 
**Initial code to review**
```python
def debtors(user, branch_id):
    rows = []
    for inv in Invoice.objects.filter(branch_id=branch_id):
        paid = sum(p.amount for p in inv.payments.all())
        if inv.total != paid:
            rows.append({"id": inv.pk, "due": inv.total - paid})
    return rows
```
 
**Expected behavior**
- Only `issued` invoices belonging to the **user's active branch** are displayed.
- `due` = invoice total **minus the sum of `settled` payments**.
- **Only positive debt** is returned.
- Output ordered by **ascending id**, with **the same structure as before**.
**Sample / acceptance**
- Invoice **300** with a `settled` payment of **120** and a `pending` payment of **100** → `due` must be **180**.
- A **settled**, **cancelled**, or **other-branch** invoice must not be in the output.
**Constraints & deliverables**
- **Keep the function signature and the output keys.**
- Branch access is determined from an **active Membership**.
- **At most 3 Queries for 100 invoices.**
- Deliver: **defect report, test of the previous correct behavior (regression test), and the corrected version.**
---
 
## Task 8: Recoverable receipt dispatch
*Celery & Redis · Senior · 5 h*
 
**Scenario & mission**
After a payment is recorded, the receipt must be announced to a service with **Celery**. The test service makes **only one message per fixed key** and returns the result for a repeated request. **Replace this service with a Fake.**
 
**Expected behavior**
- **A Rollback of the payment must not create a message.**
- **A hard Broker crash after Commit must not lose the receipt.**
- **Temporary errors**: up to **5 attempts with increasing intervals**.
- **Permanent error**: recorded directly and stopped.
- **An operator must be able to re-pursue a failed dispatch.**
**Sample / acceptance**
- The service **accepts the message but the response times out**. After recovery there must be **exactly one external message and one successful local receipt**.
- **Two Workers** for one payment must give the same result.
**Constraints & deliverables**
- **Redis as Broker; PostgreSQL for durable state.**
- Deliver: **Fake Worker contract, recovery path, crash test at the boundary of dispatch and result recording, and a guide to observing failed attempts.**
---
 
## Task 9: Reservation cancellation policy test
*pytest & Quality Engineering · Mid · 3 h*
 
**Scenario & mission**
For the **cancel** operation, build a minimal implementation and an **independent test suite**. The owner **or** the manager of the same branch can cancel a `confirmed` reservation **before it starts**. The base amount is **the collected payment**.
 
**Expected behavior**
- **At least 24 hours remaining → full refund.**
- **Between 2 hours and 24 hours (including the 2h and 24h boundaries) → half the amount, rounded down.**
- **Less than 2 hours → zero.**
- **Recording the cancellation and recording the refund document must be atomic.**
- A **repeat is allowed** and returns the previous result.
**Sample / acceptance**
- For a **101 rial** payment: **exactly 24 hours remaining → 101**, **one second later → 50**.
- **Exactly 2 hours remaining → 50**, **one second later → zero**.
- **At the start instant, the new request is rejected.**
**Constraints & deliverables**
- Use **pytest and pytest-django**.
- Write **Permission, Unit, Integration, and Failure** tests.
- **Control the clock.**
- **Simulate a document-writing failure.**
- **Introduce three deliberate defects; report which test catches each one (by test name).**
---
 
## Task 10: Multi-branch ERP architecture
*System Design & operations · Senior · 4 h*
 
**Scenario & mission**
Design the **Backend architecture** for **80 sports branches** with **court reservation, online payment, and financial reporting**. At peak sales we have **300 reservation requests and 3000 capacity-view requests per second**. A single court may be the target of **half of the reservation requests** (hot court).
 
**Expected behavior**
- A **temporary reservation is valid for 10 minutes.**
- **Active intervals of one court must not overlap.**
- Specify the handling of **late payment and repeated Callback**.
- **A branch manager sees only their own data; the central finance manager sees the aggregate report.**
- **The report may be delayed up to 5 minutes.**
**Sample / acceptance**
- Two customers choose the same interval. The **first customer's payment, after expiry and hand-over to the second customer, is confirmed** (late payment). Show **step by step**: the **reservation status, the money, the user message, and the financial reconciliation path**.
**Constraints & deliverables**
- Design document must include: **API boundary, ERD, sequence diagram, capacity model, SLO, indicators and alerts, recovery plan, and load test.**
- **Target: p95 of capacity viewing = 250 ms.**
- **Document the assumptions and two decisions that carry a cost or limitation.**
- **Implementation is not required.**
---
 
## ⚠ Interpretation notes (items to confirm or sanity-check)
 
1. **T1 sample**: confirmed against the PDF's text layer: `[(1,A,7),(3,C,4)]` and `[(1,A,7),(2,B,5)]` give A, B, C; changing A's amount to 8 in the second stream must raise an error.
2. **T1 "error before publishing"**: all copies of a `(time, id)` key must be compared **before** that key is yielded.
3. **T3 "confirmed" / "successful"**: assumed to mean Booking status `confirmed` and Payment status `success`. Failed payments are excluded from collected sums.
4. **T5 "409"** is used for all conflict cases (capacity full, second reservation by the same user, key reuse on another class).
5. **T9 "confirmed"** is the Reservation status; "owner or branch manager" are the only allowed actors.
6. **T10 "half of requests"** is read as: hot-court contention, so design must handle one court taking ~150 reservation requests per second.
7. Task hours are the company's **estimates**, not limits.
 
