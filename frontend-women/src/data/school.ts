/**
 * Demo data for the Qalamestan mentorship dashboard.
 * Browser-safe: shared by UI components and the server-side assistant (retrieval context).
 */

export const COMPETENCY_AXES = [
  { key: "scientific", label: "علمی" },
  { key: "skill", label: "مهارتی" },
  { key: "ethical", label: "اخلاقی" },
  { key: "entrepreneurial", label: "کارآفرینی" },
  { key: "social", label: "اجتماعی" },
  { key: "cultural", label: "فرهنگی" },
] as const;

export type CompetencyKey = (typeof COMPETENCY_AXES)[number]["key"];
export type Competencies = Record<CompetencyKey, number>;

export type AcademicStatus = "excellent" | "growing" | "attention" | "risk";

export const STATUS_META: Record<AcademicStatus, { label: string; tone: "success" | "info" | "warning" | "destructive" }> = {
  excellent: { label: "درخشان", tone: "success" },
  growing: { label: "رو به رشد", tone: "info" },
  attention: { label: "نیازمند توجه", tone: "warning" },
  risk: { label: "نیازمند مداخله", tone: "destructive" },
};

export const MISSION_TRACKS = [
  "فناوری و نوآوری",
  "سلامت و زیست‌بوم",
  "هنر و رسانه",
  "کارآفرینی اجتماعی",
  "پژوهش علوم پایه",
] as const;
export type MissionTrack = (typeof MISSION_TRACKS)[number];

export const GRADES = ["هفتم", "هشتم", "نهم", "دهم"] as const;
export type Grade = (typeof GRADES)[number];

export interface Observation {
  text: string;
  mentor: string;
  date: string; // Persian display date
  kind: "kudos" | "suggestion" | "alert";
}

export interface Student {
  id: string;
  name: string;
  grade: Grade;
  classroom: string;
  track: MissionTrack;
  status: AcademicStatus;
  gpa: number; // out of 20
  mathScore: number; // out of 20
  competencies: Competencies;
  observations: Observation[];
}

export const STUDENTS: Student[] = [
  {
    id: "s1", name: "آرین محمدی", grade: "نهم", classroom: "۹-الف", track: "فناوری و نوآوری", status: "excellent", gpa: 19.2, mathScore: 19.5,
    competencies: { scientific: 92, skill: 88, ethical: 81, entrepreneurial: 76, social: 70, cultural: 74 },
    observations: [
      { text: "رهبری تیم رباتیک در مسابقه منطقه‌ای؛ تقسیم کار منصفانه و آرام.", mentor: "خانم رضایی", date: "۱۹ آبان", kind: "kudos" },
      { text: "پیشنهاد: تمرین ارائه شفاهی برای جلسه داوری پروژه.", mentor: "آقای کریمی", date: "۱۲ آبان", kind: "suggestion" },
    ],
  },
  {
    id: "s2", name: "نازنین حسینی", grade: "نهم", classroom: "۹-ب", track: "سلامت و زیست‌بوم", status: "growing", gpa: 17.4, mathScore: 15.8,
    competencies: { scientific: 78, skill: 74, ethical: 90, entrepreneurial: 62, social: 85, cultural: 80 },
    observations: [
      { text: "طراحی کمپین کاهش پسماند مدرسه؛ همکاری عالی با هم‌گروهی‌ها.", mentor: "خانم نوری", date: "۱۸ آبان", kind: "kudos" },
    ],
  },
  {
    id: "s3", name: "محمدرضا کاظمی", grade: "نهم", classroom: "۹-الف", track: "پژوهش علوم پایه", status: "risk", gpa: 13.1, mathScore: 9.75,
    competencies: { scientific: 54, skill: 60, ethical: 78, entrepreneurial: 48, social: 58, cultural: 66 },
    observations: [
      { text: "افت محسوس در دو آزمون اخیر ریاضی؛ غیبت در کلاس رفع اشکال.", mentor: "آقای کریمی", date: "۲۰ آبان", kind: "alert" },
      { text: "علاقه زیاد به آزمایش‌های فیزیک؛ می‌تواند مسیر انگیزشی باشد.", mentor: "خانم رضایی", date: "۱۰ آبان", kind: "suggestion" },
    ],
  },
  {
    id: "s4", name: "ستایش احمدی", grade: "هشتم", classroom: "۸-ج", track: "هنر و رسانه", status: "excellent", gpa: 18.9, mathScore: 17.6,
    competencies: { scientific: 80, skill: 91, ethical: 86, entrepreneurial: 72, social: 88, cultural: 95 },
    observations: [
      { text: "ساخت مستند کوتاه «صدای محله» با مشارکت ساکنان؛ بازخورد فوق‌العاده.", mentor: "خانم صالحی", date: "۱۷ آبان", kind: "kudos" },
    ],
  },
  {
    id: "s5", name: "امیرحسین رحیمی", grade: "دهم", classroom: "۱۰-الف", track: "کارآفرینی اجتماعی", status: "growing", gpa: 16.8, mathScore: 15.2,
    competencies: { scientific: 70, skill: 79, ethical: 82, entrepreneurial: 93, social: 87, cultural: 71 },
    observations: [
      { text: "راه‌اندازی بازارچه محصولات دست‌ساز به نفع خیریه؛ مدیریت مالی دقیق.", mentor: "آقای موسوی", date: "۱۶ آبان", kind: "kudos" },
    ],
  },
  {
    id: "s6", name: "هلیا جعفری", grade: "هفتم", classroom: "۷-الف", track: "پژوهش علوم پایه", status: "attention", gpa: 15.3, mathScore: 12.5,
    competencies: { scientific: 68, skill: 62, ethical: 88, entrepreneurial: 55, social: 64, cultural: 79 },
    observations: [
      { text: "در کار گروهی کم‌حرف است؛ اعتمادبه‌نفس در کلاس ریاضی پایین آمده.", mentor: "خانم نوری", date: "۱۹ آبان", kind: "alert" },
    ],
  },
  {
    id: "s7", name: "پارسا قربانی", grade: "دهم", classroom: "۱۰-ب", track: "فناوری و نوآوری", status: "excellent", gpa: 19.6, mathScore: 20,
    competencies: { scientific: 96, skill: 90, ethical: 76, entrepreneurial: 84, social: 66, cultural: 68 },
    observations: [
      { text: "کسب رتبه اول المپیاد برنامه‌نویسی استان؛ آماده نقش منتور همتا.", mentor: "آقای کریمی", date: "۱۵ آبان", kind: "kudos" },
    ],
  },
  {
    id: "s8", name: "ریحانه مرادی", grade: "هشتم", classroom: "۸-الف", track: "سلامت و زیست‌بوم", status: "growing", gpa: 17.1, mathScore: 14.9,
    competencies: { scientific: 76, skill: 70, ethical: 92, entrepreneurial: 60, social: 90, cultural: 84 },
    observations: [
      { text: "پیگیری منظم باغچه هوشمند مدرسه؛ ثبت دقیق داده‌های رطوبت خاک.", mentor: "خانم صالحی", date: "۱۸ آبان", kind: "kudos" },
    ],
  },
  {
    id: "s9", name: "علی‌اصغر نجفی", grade: "هفتم", classroom: "۷-ب", track: "هنر و رسانه", status: "attention", gpa: 14.6, mathScore: 11.25,
    competencies: { scientific: 58, skill: 75, ethical: 80, entrepreneurial: 64, social: 72, cultural: 88 },
    observations: [
      { text: "تمرکز کوتاه در کلاس‌های صبح؛ پیشنهاد گفت‌وگو با خانواده درباره خواب.", mentor: "خانم رضایی", date: "۲۰ آبان", kind: "alert" },
    ],
  },
  {
    id: "s10", name: "مهسا کریم‌زاده", grade: "دهم", classroom: "۱۰-الف", track: "پژوهش علوم پایه", status: "excellent", gpa: 19.0, mathScore: 18.75,
    competencies: { scientific: 94, skill: 82, ethical: 85, entrepreneurial: 66, social: 74, cultural: 77 },
    observations: [
      { text: "مقاله پژوهشی درباره کیفیت آب قنات‌ها پذیرفته شد.", mentor: "آقای موسوی", date: "۱۴ آبان", kind: "kudos" },
    ],
  },
  {
    id: "s11", name: "یاسین عباسی", grade: "هشتم", classroom: "۸-ب", track: "کارآفرینی اجتماعی", status: "risk", gpa: 12.7, mathScore: 10.5,
    competencies: { scientific: 52, skill: 66, ethical: 70, entrepreneurial: 74, social: 61, cultural: 63 },
    observations: [
      { text: "سه غیبت متوالی و عدم تحویل تکالیف؛ نیاز به جلسه مشاوره فوری.", mentor: "خانم نوری", date: "۲۱ آبان", kind: "alert" },
    ],
  },
  {
    id: "s12", name: "فاطمه زهرا شریفی", grade: "نهم", classroom: "۹-ب", track: "هنر و رسانه", status: "growing", gpa: 17.9, mathScore: 16.4,
    competencies: { scientific: 74, skill: 86, ethical: 89, entrepreneurial: 70, social: 82, cultural: 93 },
    observations: [
      { text: "طراحی پوستر هفته کتاب؛ ایده‌پردازی خلاقانه و اجرای تمیز.", mentor: "خانم صالحی", date: "۱۷ آبان", kind: "kudos" },
    ],
  },
];

export interface KpiMetric {
  id: string;
  label: string;
  value: string;
  delta: string;
  deltaLabel: string;
  trend: "up" | "down";
  tone: "primary" | "success" | "warning" | "info";
  series: number[];
}

export const KPIS: KpiMetric[] = [
  { id: "mentees", label: "متربیان فعال", value: "۴۱۲", delta: "+۱۲", deltaLabel: "این ماه", trend: "up", tone: "primary", series: [372, 380, 378, 389, 394, 398, 405, 412] },
  { id: "projects", label: "پروژه‌های مأموریتی در جریان", value: "۳۸", delta: "+۵", deltaLabel: "این هفته", trend: "up", tone: "info", series: [24, 27, 29, 30, 31, 33, 33, 38] },
  { id: "growth", label: "شاخص رشد تربیتی و درسی", value: "۸۷٪", delta: "+۴٪", deltaLabel: "رشد ماهانه", trend: "up", tone: "success", series: [78, 79, 81, 80, 83, 84, 85, 87] },
  { id: "observations", label: "مشاهدات و جلسات مربیگری", value: "۱٬۲۴۸", delta: "+۸۶", deltaLabel: "هفته جاری", trend: "up", tone: "warning", series: [960, 1010, 1040, 1085, 1120, 1162, 1190, 1248] },
];

/** School-wide competency averages vs. the mission target, per grade. */
export const RADAR_BY_GRADE: Record<"all" | Grade, Competencies> = {
  all: { scientific: 78, skill: 76, ethical: 84, entrepreneurial: 68, social: 75, cultural: 79 },
  هفتم: { scientific: 70, skill: 69, ethical: 86, entrepreneurial: 60, social: 70, cultural: 82 },
  هشتم: { scientific: 74, skill: 77, ethical: 84, entrepreneurial: 68, social: 79, cultural: 81 },
  نهم: { scientific: 80, skill: 78, ethical: 85, entrepreneurial: 67, social: 74, cultural: 78 },
  دهم: { scientific: 86, skill: 82, ethical: 81, entrepreneurial: 79, social: 76, cultural: 74 },
};

export const RADAR_TARGET: Competencies = { scientific: 85, skill: 85, ethical: 90, entrepreneurial: 80, social: 85, cultural: 85 };

export type StreamKind = "milestone" | "kudos" | "alert";

export interface StreamItem {
  id: string;
  kind: StreamKind;
  title: string;
  body: string;
  studentId?: string;
  author: string;
  time: string;
  tag: string;
}

export const STREAM: StreamItem[] = [
  { id: "e1", kind: "milestone", title: "پارسا قربانی به سطح «منتور همتا» رسید", body: "پس از کسب رتبه اول المپیاد برنامه‌نویسی، پارسا آماده هدایت گروه مطالعه پایه هشتم است.", studentId: "s7", author: "سامانه رشد", time: "۱۰ دقیقه پیش", tag: "فناوری و نوآوری" },
  { id: "e2", kind: "alert", title: "هشدار افت ریاضی — محمدرضا کاظمی", body: "میانگین دو آزمون اخیر ۹٫۷۵ از ۲۰. پیشنهاد مشاور: جلسه سه‌جانبه با خانواده و برنامه رفع اشکال هفتگی.", studentId: "s3", author: "خانم نوری (مشاور)", time: "۳۵ دقیقه پیش", tag: "ریاضی پایه نهم" },
  { id: "e3", kind: "kudos", title: "تشویق معلم برای ستایش احمدی", body: "مستند «صدای محله» نمونه درخشان شایستگی فرهنگی و اجتماعی بود. 👏", studentId: "s4", author: "خانم صالحی", time: "۱ ساعت پیش", tag: "هنر و رسانه" },
  { id: "e4", kind: "milestone", title: "پروژه بازارچه خیریه به هدف مالی رسید", body: "تیم امیرحسین رحیمی ۱۲۰٪ هدف را محقق کرد و گزارش شفاف مالی ارائه داد.", studentId: "s5", author: "سامانه رشد", time: "۲ ساعت پیش", tag: "کارآفرینی اجتماعی" },
  { id: "e5", kind: "alert", title: "الگوی غیبت — یاسین عباسی", body: "سه غیبت متوالی ثبت شده است. نیاز به تماس با خانواده تا پایان امروز.", studentId: "s11", author: "معاون پرورشی", time: "۳ ساعت پیش", tag: "حضور و غیاب" },
  { id: "e6", kind: "kudos", title: "قدردانی از ریحانه مرادی", body: "ثبت منظم داده‌های باغچه هوشمند، الگوی دقت علمی برای کلاس شد.", studentId: "s8", author: "خانم صالحی", time: "دیروز", tag: "سلامت و زیست‌بوم" },
];

/** Knowledge base the assistant retrieves from and cites. */
export interface KnowledgeDoc {
  id: string;
  title: string;
  source: string;
  content: string;
}

export const KNOWLEDGE_BASE: KnowledgeDoc[] = [
  {
    id: "kb-framework",
    title: "چارچوب شایستگی‌های شش‌گانه قلمستان",
    source: "سند تحول مأموریت‌محور — نسخه ۱۴۰۵",
    content:
      "شش محور شایستگی: علمی (تفکر نقاد، حل مسئله، سواد ریاضی)، مهارتی (کار با ابزار، فناوری، ارائه)، اخلاقی (صداقت، مسئولیت‌پذیری، انصاف)، کارآفرینی (ایده‌پردازی، ریسک‌پذیری سنجیده، مدیریت منابع)، اجتماعی (همکاری، همدلی، رهبری) و فرهنگی (هویت، هنر، زبان). نمره زیر ۶۰ در هر محور نیازمند برنامه رشد انفرادی است و نمره بالای ۸۵ نشانه آمادگی برای نقش منتور همتاست.",
  },
  {
    id: "kb-irp",
    title: "راهنمای برنامه رشد انفرادی (IRP)",
    source: "معاونت آموزشی — دستورالعمل ۳/۱۲",
    content:
      "برنامه رشد انفرادی شامل: ۱) شناسایی دو محور ضعیف و یک محور قوت، ۲) تعریف هدف هوشمند ۶ هفته‌ای، ۳) یک مأموریت کوچک واقعی متصل به علاقه دانش‌آموز، ۴) جلسه مربیگری ۱۵ دقیقه‌ای هفتگی، ۵) بازبینی با خانواده در هفته سوم و ششم. از نقطه قوت برای ساختن انگیزه در محور ضعیف استفاده شود.",
  },
  {
    id: "kb-observation",
    title: "دستورالعمل ثبت مشاهده رفتاری و تربیتی",
    source: "واحد مشاوره — شیوه‌نامه ثبت مشاهده",
    content:
      "مشاهده باید عینی، زمان‌دار و رفتاری باشد (چه دیدم، کجا، چه زمانی)، از برچسب‌زنی پرهیز شود. هر مشاهده یکی از سه نوع است: تشویق، پیشنهاد رشد، هشدار. هشدارهای مربوط به ایمنی یا غیبت بیش از دو روز متوالی باید ظرف ۲۴ ساعت به مشاور ارجاع شود. حداقل نسبت تشویق به هشدار ۳ به ۱ توصیه می‌شود.",
  },
  {
    id: "kb-math",
    title: "گزارش پایش ریاضی پایه‌های هفتم تا نهم — آبان",
    source: "گروه آموزشی ریاضی",
    content:
      "میانگین ریاضی پایه نهم ۱۵٫۹ و پایه هفتم ۱۴٫۲ است. بیشترین افت در مبحث معادلات و عبارت‌های جبری دیده شد. دانش‌آموزان با نمره زیر ۱۲ در دو آزمون متوالی در گروه «نیازمند توجه» قرار می‌گیرند. راهکار پیشنهادی: کلاس رفع اشکال گروه‌های کوچک، تمرین‌های بازی‌وار و استفاده از منتورهای همتا از پایه دهم.",
  },
  {
    id: "kb-intervention",
    title: "پروتکل مداخله مشاوره‌ای سه‌سطحی",
    source: "واحد مشاوره — پروتکل ۱۴۰۵",
    content:
      "سطح ۱ (همگانی): بازخورد مثبت و پیگیری معلم. سطح ۲ (هدفمند): جلسه مشاوره فردی، برنامه رفع اشکال و اطلاع به خانواده. سطح ۳ (فشرده): جلسه سه‌جانبه دانش‌آموز، خانواده و مشاور، برنامه رشد انفرادی و پیگیری هفتگی مدیر. افت ناگهانی تحصیلی همراه با غیبت مستقیماً سطح ۲ یا ۳ است.",
  },
  {
    id: "kb-missions",
    title: "راهنمای پروژه‌های مأموریتی",
    source: "دفتر مأموریت‌های قلمستان",
    content:
      "هر پروژه مأموریتی یک مسئله واقعی محله یا مدرسه را هدف می‌گیرد و ۸ تا ۱۲ هفته طول می‌کشد. مسیرهای مأموریتی: فناوری و نوآوری، سلامت و زیست‌بوم، هنر و رسانه، کارآفرینی اجتماعی، پژوهش علوم پایه. ارزیابی بر اساس اثر واقعی، کار تیمی، مستندسازی و ارائه نهایی انجام می‌شود. دانش‌آموزان در معرض خطر بهتر است در نقش‌های کوچک و موفقیت‌محور وارد پروژه شوند.",
  },
  {
    id: "kb-weekly",
    title: "خلاصه پایش هفتگی مدرسه — هفته سوم آبان",
    source: "داشبورد مدیریتی قلمستان",
    content:
      "۴۱۲ متربی فعال (۱۲+ در ماه)، ۳۸ پروژه مأموریتی در جریان (۵+ این هفته)، شاخص رشد تربیتی و درسی ۸۷٪ (۴٪+ ماهانه)، ۱۲۴۸ مشاهده و جلسه مربیگری ثبت‌شده (۸۶+ این هفته). محور کارآفرینی با میانگین ۶۸ پایین‌ترین و محور اخلاقی با ۸۴ بالاترین محور مدرسه است.",
  },
];

export function rosterDigest(students: Student[] = STUDENTS): string {
  return students
    .map((s) => {
      const comp = COMPETENCY_AXES.map((a) => `${a.label} ${s.competencies[a.key]}`).join("، ");
      const obs = s.observations[0];
      return `- ${s.name} | پایه ${s.grade} کلاس ${s.classroom} | مسیر: ${s.track} | وضعیت: ${STATUS_META[s.status].label} | معدل ${s.gpa} | ریاضی ${s.mathScore} | شایستگی‌ها: ${comp} | آخرین مشاهده (${obs?.mentor ?? "-"}، ${obs?.date ?? "-"}): ${obs?.text ?? "-"}`;
    })
    .join("\n");
}
