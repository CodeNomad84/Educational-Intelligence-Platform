# DEMO SCRIPT — 10 minutes (DEMO SCOPE)

**Audience:** School CEO · Planning manager · Counseling-center manager.
**Story:** Problem → Insight → Action → Impact. No technical vocabulary on stage (no "rules engine", roles, API, RAG).
**Language:** Persian (talking points below). Say once, early: «همهٔ دانش‌آموزان این نمایش فرضی‌اند.»

**Characters (synthetic, fixed by the seed — see `DEMO_GUIDE.md` §5)**

| | Character | Where | Role in the story |
|---|---|---|---|
| A | **رضا کاظمی** (۹-ب) | `/demo/students/?q=رضا` | High: attendance, maths and behaviour all slipping |
| B | **علی احمدی** (۱۰-الف) | list or counselor page | Medium: early-warning signs |
| C | **مهسا فرهادی** (۱۰-ب) | `/demo/students/?q=مهسا` | Improved after intervention |
| D | **آرین جعفری** (۱۱-الف) | `/demo/students/?q=آرین` | Excellent — the system is not only about problems |

Do **not** read exact figures from this script; read the numbers that are on the screen. The counts 40 / 2 / 7 / 31 are guaranteed by the seed.

---

## Minute 0 – 1.5 · PROBLEM — "We cannot see it coming"
*Screen: demo login (no typing yet), then log in as `demo_admin`; stay on the dashboard top.*

* «مدرسه هر روز هزاران داده تولید می‌کند: حضور و غیاب، نمرات، مشاهدات معلم‌ها، جلسات مشاوره. اما این داده‌ها جاهای مختلفی هستند.»
* «معمولاً افت یک دانش‌آموز را وقتی می‌بینیم که کارنامه آمده و دیر شده است.»
* «سؤال این پلتفرم یک جمله است: **امروز چه کسی به توجه نیاز دارد، و چرا؟**»

## Minute 1.5 – 5 · INSIGHT — "One view, early signals"
*Screen: `/dashboard/`.*

1. **Top cards** — «۴۰ دانش‌آموز؛ ۲ نفر پرخطر، ۷ نفر نیازمند توجه، بقیه وضعیت پایدار.» (CEO: the whole school in one glance.)
2. **Doughnut + trends** — «روند غیبت و نمرات مدرسه هفته به هفته؛ برای برنامه‌ریزی (planning manager): کدام دوره‌ها و کلاس‌ها نگران‌کننده‌اند.»
3. **Class table** — «کدام کلاس بیشترین موارد را دارد.»
4. **Students needing attention** — «فهرست اولویت‌بندی‌شده، هر کدام با مهم‌ترین دلیل.»
5. Open **Counselor dashboard** (`/demo/counselor/`) — «مشاور به‌جای گشتن در پرونده‌ها، مستقیم موارد را با دلیل و اقدام پیشنهادی می‌بیند.»

## Minute 5 – 8 · ACTION — "Why, and what to do"
*Screen: student A, then C, then (if time) B.*

1. **Student A — رضا کاظمی.** Open the profile.
   * «سطح پرخطر. به‌جای یک عدد مبهم، دلیل‌ها را می‌بینیم:» read the 3–4 reasons aloud with the numbers on screen (attendance fall, maths fall, repeated observations).
   * «کنار هر دلیل، امتیازش و نام قاعده‌اش هست؛ هیچ جعبهٔ سیاهی نیست و مشاور می‌تواند نقد کند.»
2. **Recommended actions** (right card) — «تماس با خانواده، برنامهٔ پیگیری حضور، پشتیبانی درسی ریاضی، جلسهٔ مشاوره. پیشنهاد است؛ تصمیم با مشاور است.»
3. **Student C — مهسا فرهادی** — «همین سیستم اثر اقدام را هم نشان می‌دهد: پس از جلسات مشاوره و برنامهٔ حضور، غیبت پایین آمده و نمره بالا رفته.» Then in the **assistant** ask: «مهسا فرهادی چگونه بهتر شد؟» — read: previous state → intervention → current state → evidence.
4. **Assistant for the room** — ask: «کدام دانش‌آموزان نیاز به توجه دارند؟» «این دستیار مدل زبانی نیست؛ فقط از همین داده‌ها و قواعد پاسخ می‌دهد و همیشه می‌نویسد بازبینی انسانی لازم است.»
5. (Optional, 20 s) **Student D — آرین جعفری**: «نقاط قوت را هم می‌بینیم؛ فقط دنبال مشکل نیست.»

## Minute 8 – 9 · IMPACT — "What changes for you"
*Screen: back on the dashboard.*

* **مدیر:** «تصمیم‌گیری بر اساس تصویر یک‌پارچه، نه گزارش‌های پراکنده.»
* **برنامه‌ریزی:** «روند و مقایسهٔ کلاس‌ها؛ منابع را جایی ببریم که لازم است.»
* **مشاوره:** «زمان کمتر برای پیدا کردن موارد، زمان بیشتر برای گفت‌وگو با دانش‌آموز و خانواده.»
* «اثر واقعی را در یک دورهٔ آزمایشی با داده و معیارهای خودتان اندازه می‌گیریم؛ اعداد امروز نمایشی‌اند.»

## Minute 9 – 10 · ROADMAP and ask

| Today (this demo) | Next | Later |
|---|---|---|
| Transparent early-warning on synthetic data | Pilot on your real data under your data-protection policy; counselor/teacher roles by class; alert → review → follow-up workflow; family portal | Search over school documents and AI-written summaries — always cited, always reviewed by a human |

* «هوش مصنوعی در این پلتفرم مشورتی است؛ هیچ تصمیمی را خودکار نمی‌گیرد.»
* «تا وقتی چارچوب امنیت و حریم خصوصی تکمیل نشده، داده واقعی وارد نمی‌شود.»
* Close with three questions, one per person: CEO — «کدام تصمیم هفتگی را می‌خواهید با این تصویر بگیرید؟» · Planning — «چه شاخص‌هایی گزارش می‌دهید؟» · Counseling — «در عمل چه اقداماتی انجام می‌دهید و چه چیزی در پیشنهادها کم است؟»

---

## Do / don't on stage
* Do not open the parent view or type URLs; navigate only with the top bar and the profile buttons. (Parent portal = a future phase.)
* Do not promise accuracy figures; say "to be calibrated with your counselors".
* If asked "is this AI?": «اکنون یک موتور قاعده‌محور شفاف است، عمداً؛ هوش مصنوعی در گام‌های بعد، مشورتی و با منبع.»

## Likely questions
| Question | Answer |
|---|---|
| «داده‌ها واقعی‌اند؟» | No — fully synthetic; names and IDs are fictional. |
| «آستانه‌ها از کجا آمده؟» | Demo assumptions, configurable; to be calibrated with your counselors. |
| «می‌تواند اشتباه کند؟» | Yes; it shows data confidence, explains every point and always needs human review. |
| «والدین چه می‌بینند؟» | Not in this demo. A family portal and what families should see is a later, policy-driven phase. |
| «این با نرم‌افزار فعلی ما چه فرقی دارد؟» | It joins attendance, grades and observations into one explained early-warning view. |
