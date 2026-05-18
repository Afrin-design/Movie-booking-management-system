# BookMyShow — Complete App Guide & Flow

---

## 🚀 How to Start the App

```bash
cd bookmyshow_fixed_v2
pip install -r requirements.txt --break-system-packages
cp .env.example .env          # Edit with your DB URL & mail config
python app.py                 # Starts at http://localhost:5000
```

**Default Admin Login:**
- Email: `admin@gmail.com`
- Password: `admin123`

---

## 👤 User Roles

| Role           | Access                                          |
|----------------|-------------------------------------------------|
| `user`         | Browse movies, book seats, pay, view history    |
| `theater_owner`| Manage their screens, schedule shows, see bookings |
| `admin`        | Full control — movies, theaters, users, reports |

---

## 🎬 User Flow (Public / Customer)

```
Home (/) 
  → Browse featured movies
  → Filter by city / genre
  → Click a movie
        ↓
Movie Detail (/movies/<id>)
  → See shows grouped by theater
  → Click a showtime
        ↓
Seat Selection (/shows/<id>/seats)
  → See Gold / Silver / General seats (colour-coded)
  → Click seats to select (turns highlighted)
  → Click "Confirm Booking" (redirects to login if not logged in)
        ↓
[Login / Register if needed]
        ↓
Payment Page (/payment/<booking_id>)
  → Choose UPI / Card / Netbanking
  → Click "Pay Now"
        ↓
Booking Confirmation (/booking/confirmation/<id>)
  → See ticket details, seat numbers, total paid
        ↓
Dashboard (/dashboard)
  → View all past bookings & payment status
```

---

## 🏠 Theater Owner Flow

**Login → redirects to `/owner/` (Dashboard)**

### Sidebar Sections

| Section       | What it shows                                               |
|---------------|-------------------------------------------------------------|
| Dashboard     | Stats: Theaters · Screens · Shows · Bookings · Revenue      |
| Screens       | All screens across your theaters (with badge count)        |
| Shows         | All scheduled shows (with badge count)                     |
| Bookings      | All customer bookings for your theater (with badge count)  |
| Add Screen    | Form to create a new screen                                |
| Schedule Show | Form to add a new show                                     |

### How to Set Up (First Time)
1. Admin creates your account → you receive temp password by email
2. Log in → you're forced to change password
3. Admin assigns a Theater to your account
4. Go to **Screens → Add Screen**: enter screen number + Gold/Silver/General seat counts → seats auto-generated in DB
5. Go to **Shows → Schedule Show**: pick movie, theater, screen, date, time, price
6. Users can now see your shows and book seats!

### Workflow: Add a Screen
```
Sidebar → Add Screen
  → Select Theater (dropdown)
  → Enter Screen Number (e.g. 1, 2, 3)
  → Enter Gold Seats count (e.g. 20)
  → Enter Silver Seats count (e.g. 40)
  → Enter General Seats count (e.g. 60)
  → Submit → Screen + all seats created in DB automatically
```

### Workflow: Schedule a Show
```
Sidebar → Schedule Show
  → Select Theater
  → Select Movie (from admin-managed list)
  → Select Screen (filters to your theater's screens)
  → Pick Show Date (calendar)
  → Enter Start Time (e.g. 18:30)
  → Enter Price Per Ticket (e.g. 200)
  → Enter Available Seats (usually = screen's total seats)
  → Submit → Show live immediately, users can book
```

---

## 🛡️ Admin Flow

**Login → redirects to `/admin/` (Dashboard)**

### Sidebar Sections

| Section       | URL                     | Purpose                              |
|---------------|-------------------------|--------------------------------------|
| Dashboard     | /admin/                 | Revenue charts, monthly bookings, genre breakdown |
| Movies        | /admin/movies           | Add / Edit / Delete movies           |
| Theaters      | /admin/theaters         | Add / Edit / Delete theaters         |
| Shows         | /admin/shows            | View all shows, add new              |
| All Users     | /admin/users            | See all users, change roles          |
| Create Owner  | /admin/users/create-owner | Create a theater owner account    |
| All Bookings  | /admin/bookings         | Every booking ever made              |
| Messages      | /admin/messages         | Contact form submissions from users  |

### Admin Typical Workflow
```
1. Add Movie (Movies → Add Movie)
   → Title, Genre, Language, Duration, Rating, Release Date, Description

2. Add Theater Owner (Users → Create Owner)
   → Name, Email, Phone → temp password auto-generated & emailed

3. Add Theater (Theaters → Add Theater)
   → Name, Location, City, State → assign to a Theater Owner

4. [Theater Owner logs in and adds Screens + Shows]

5. Monitor:
   → All Bookings → see every ticket purchased
   → Dashboard → revenue charts, monthly trends
   → Messages → customer support queries
```

---

## 🗄️ Database: How Data is Saved Dynamically

**Every form submission saves directly to the DB — no static data.**

| Action                     | Saved To                  | Auto-generated ID |
|----------------------------|---------------------------|-------------------|
| Register user              | `users` table             | `US_1, US_2, …`  |
| Admin adds movie           | `movies` table            | `MV_1, MV_2, …`  |
| Admin adds theater         | `theaters` table          | `TH_1, TH_2, …`  |
| Owner adds screen          | `screens` + `seats` tables| `SC_1, SC_2, …` + `ST_1, ST_2, …` |
| Owner schedules show       | `shows` table             | `SH_1, SH_2, …`  |
| User confirms booking      | `bookings` table          | `BK_1, BK_2, …`  |
| User pays                  | `payments` table          | `PMT_1, PMT_2, …`|
| User sends contact message | `messages` table          | Auto int PK       |

**Seat generation is fully automatic:** when you add a screen with 20 Gold + 40 Silver + 60 General, the app creates 120 individual seat rows (G1–G20, S1–S40, R1–R60) in the `seats` table automatically.

---

## ⚠️ Common Issues & Fixes

| Problem                            | Fix                                                             |
|------------------------------------|-----------------------------------------------------------------|
| Sidebar count not showing          | **Fixed** — context processor now always returns all counts     |
| Shows badge missing from sidebar   | **Fixed** — `owner_stats.shows` now populated                   |
| Booking count = 0 in sidebar       | **Fixed** — was only counting when > 0; now always accurate     |
| Payment email error                | **Fixed** — now uses the global `mail` object from `app.py`     |
| Dashboard missing Shows stat card  | **Fixed** — 5th stat card added                                 |
| Bookings page had no summary stats | **Fixed** — 4 stat cards now shown at top of bookings page      |

---

## 🔑 Auth Flow

```
/auth/login        → Login form
/auth/register     → New user registration
/auth/logout       → Clears session
/auth/change-password → Required after first login for owners
/auth/forgot-password → Email reset flow (needs MAIL config)
```

After login, users are redirected based on role:
- `admin` → `/admin/`
- `theater_owner` → `/owner/`
- `user` → `/` (home)

---

## 📬 Email Setup (optional)

Edit `.env`:
```
MAIL_USERNAME=your@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your@gmail.com
```

Emails sent for:
- Owner account creation (temp password)
- Booking confirmation to user
- Password reset token

---

## 🔄 Full End-to-End Booking Example

1. **Admin** adds movie "Kalki 2.0"
2. **Admin** creates theater owner → assigns theater "PVR Kurnool"
3. **Theater Owner** logs in → adds Screen #1 (20 Gold, 40 Silver, 60 General)
4. **Theater Owner** schedules show: Kalki 2.0 · Screen 1 · 2026-05-01 · 18:30 · ₹250
5. **User** visits home → picks city "Kurnool" → sees Kalki 2.0
6. **User** clicks movie → picks the 18:30 show → seat selection page appears
7. **User** selects 2 Gold seats (G1, G2) → clicks Confirm Booking
8. → If not logged in: redirected to login → after login comes back
9. **Payment page**: Total = (₹250 × 2) + (₹100 × 2 Gold charge) = ₹700
10. **User** pays via UPI → Booking Confirmed → seats marked Booked in DB
11. **Theater Owner** sees Bookings → count badge updates to 1
12. **Admin** dashboard → Bookings count + Revenue both increment

