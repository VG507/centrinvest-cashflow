const pptxgen = require("/home/ijstt/mcp-servers/ppt-mcp/node_modules/pptxgenjs");
const path = require("path");

const pptx = new pptxgen();
pptx.layout = "LAYOUT_16x9"; // 10.0 x 5.625 inches

// Modern, airy, unbloated palette (Hackathon Tech + Center-invest Case Accent)
const COLORS = {
  bgLight: "FAFAFA",            // Clean, distraction-free neutral background
  cardBg: "FFFFFF",             // Pure white cards
  cardBorder: "E2E8F0",         // Very faint gray border
  primaryGreen: "50B848",       // Center-invest brand accent
  darkGreen: "1C4119",          // Deep forest green
  textDark: "0F172A",           // Deep slate for high legibility
  textMuted: "64748B",          // Balanced slate-gray for captions
  tagDarkBg: "0F172A",          // Dark pill for Hack RND
  tagLightBg: "F1F5F9",         // Subtle gray pill
  mintBg: "F0FDF4",             // Soft mint tint
  alertRed: "DC2626"
};

const LOGO_PATH = path.resolve(__dirname, "../docs/logo_centr_invest.png");
const SCREENSHOT_PATH = path.resolve(__dirname, "../docs/screenshot_dashboard.png");

// Clean, consistent header for Slides 2-6 (Hackathon 65% / Case 35%)
function addCleanHeader(slide, title, subheader) {
  // Hackathon Top Badge
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: 0.8, y: 0.35, w: 1.6, h: 0.28,
    fill: { color: COLORS.tagDarkBg },
    rectRadius: 0.05
  });
  slide.addText("HACK RND 2026", {
    x: 0.8, y: 0.35, w: 1.6, h: 0.28,
    fontSize: 8, fontFace: "Arial", bold: true, color: "FFFFFF", align: "center", valign: "middle"
  });

  slide.addText("КЕЙС БАНКА «ЦЕНТР-ИНВЕСТ»", {
    x: 2.5, y: 0.35, w: 3.5, h: 0.28,
    fontSize: 8.5, fontFace: "Arial", bold: true, color: COLORS.textMuted, valign: "middle"
  });

  // Partner Logo in Top Right
  slide.addImage({ path: LOGO_PATH, x: 7.7, y: 0.3, w: 1.5, h: 0.32 });

  // Main Slide Title
  slide.addText(title, {
    x: 0.8, y: 0.75, w: 8.4, h: 0.45,
    fontSize: 18, fontFace: "Arial", bold: true, color: COLORS.textDark, valign: "top"
  });

  // Subheader
  if (subheader) {
    slide.addText(subheader, {
      x: 0.8, y: 1.2, w: 8.4, h: 0.3,
      fontSize: 10.5, fontFace: "Arial", color: COLORS.primaryGreen, bold: true, valign: "top"
    });
  }
}

// ============================================================================
// SLIDE 1: Title & The Hook (0:00 - 0:30)
// ============================================================================
const slide1 = pptx.addSlide();
slide1.background = { color: COLORS.bgLight };

// Top Bar: Hackathon 65% + Case 35%
slide1.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
  x: 0.8, y: 0.45, w: 2.1, h: 0.32,
  fill: { color: COLORS.tagDarkBg },
  rectRadius: 0.06
});
slide1.addText("HACK RND 2026", {
  x: 0.8, y: 0.45, w: 2.1, h: 0.32,
  fontSize: 9, fontFace: "Arial", bold: true, color: "FFFFFF", align: "center", valign: "middle"
});

slide1.addText("КЕЙС: БАНК «ЦЕНТР-ИНВЕСТ» — УЧЁТ ДЛЯ БИЗНЕСА", {
  x: 3.05, y: 0.45, w: 4.2, h: 0.32,
  fontSize: 9.5, fontFace: "Arial", bold: true, color: COLORS.textMuted, valign: "middle"
});

slide1.addImage({ path: LOGO_PATH, x: 7.45, y: 0.4, w: 1.8, h: 0.38 });

// Main Product Title
slide1.addText("ПОТОК", {
  x: 0.8, y: 1.25, w: 8.4, h: 0.9,
  fontSize: 52, fontFace: "Arial", bold: true, color: COLORS.textDark
});

slide1.addText("Предиктивный радар ликвидности и умный овердрафт для малого бизнеса", {
  x: 0.8, y: 2.18, w: 8.4, h: 0.42,
  fontSize: 16, fontFace: "Arial", bold: true, color: COLORS.primaryGreen
});

slide1.addText("Инженерное решение команды Patch_Note: аналитическое упреждение кассовых разрывов за 30 дней и бесшовная выдача финансирования в один клик.", {
  x: 0.8, y: 2.65, w: 8.2, h: 0.55,
  fontSize: 11.5, fontFace: "Arial", color: COLORS.textMuted
});

// Three Airy Metric Anchors
const s1Metrics = [
  { num: "30 дней", label: "Горизонт радара", sub: "выявление разрыва до кризиса" },
  { num: "< 5 мс", label: "Скорость ядра", sub: "аналитический расчет SDE" },
  { num: "1 клик", label: "До решения", sub: "предодобренный овердрафт банка" }
];

s1Metrics.forEach((m, i) => {
  const xPos = 0.8 + i * 2.85;
  slide1.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: xPos, y: 3.4, w: 2.65, h: 1.15,
    fill: { color: COLORS.cardBg },
    line: { color: COLORS.cardBorder, width: 1 },
    rectRadius: 0.08
  });
  slide1.addText(m.num, {
    x: xPos + 0.2, y: 3.48, w: 2.25, h: 0.42,
    fontSize: 22, fontFace: "Arial", bold: true, color: COLORS.textDark
  });
  slide1.addText(m.label, {
    x: xPos + 0.2, y: 3.9, w: 2.25, h: 0.28,
    fontSize: 10, fontFace: "Arial", bold: true, color: COLORS.primaryGreen
  });
  slide1.addText(m.sub, {
    x: xPos + 0.2, y: 4.16, w: 2.25, h: 0.28,
    fontSize: 8.5, fontFace: "Arial", color: COLORS.textMuted
  });
});

// Clean Minimalist Team Footer
slide1.addText([
  { text: "КОМАНДА PATCH_NOTE:  ", options: { bold: true, color: COLORS.textDark, fontSize: 10 } },
  { text: "Владимир Федорко ", options: { bold: true, color: COLORS.primaryGreen, fontSize: 10 } },
  { text: "(Backend & Math Core)   •   ", options: { color: COLORS.textMuted, fontSize: 9.5 } },
  { text: "Владислав Паршин ", options: { bold: true, color: COLORS.primaryGreen, fontSize: 10 } },
  { text: "(Frontend & UI/UX)   •   ", options: { color: COLORS.textMuted, fontSize: 9.5 } },
  { text: "MVP готов (89 тестов)", options: { bold: true, color: COLORS.darkGreen, fontSize: 9.5 } }
], {
  x: 0.8, y: 4.88, w: 8.4, h: 0.4,
  fontFace: "Arial", valign: "middle"
});

slide1.addNotes("Здравствуйте, эксперты и жюри Hack RND 2026! Мы команда Patch_Note: Владимир Федорко отвечает за математику и бэкенд, Владислав Паршин — за фронтенд и пользовательский опыт. В кейсе Банка «Центр-инвест» мы решаем главную проблему малого бизнеса: 90% закрывающихся компаний прибыльны по отчетам, но гибнут из-за внезапного кассового разрыва на 48 часов. Наш сервис «Поток» вычисляет кассовые ямы за 30 дней вперед и превращает кассовый стресс в одобренный овердрафт банка в один клик.");

// ============================================================================
// SLIDE 2: The Problem (0:30 - 1:00)
// ============================================================================
const slide2 = pptx.addSlide();
slide2.background = { color: COLORS.bgLight };
addCleanHeader(slide2, "ПОЧЕМУ МАЛЫЙ БИЗНЕС ТОНЕТ В КАССОВЫХ РАЗРЫВАХ", "Три слепые зоны, которые не решает классический учет в Excel");

const s2Problems = [
  {
    num: "01",
    title: "Иллюзия прибыли (P&L)",
    fact: "+1.2 млн ₽ в отчете",
    reality: "0 ₽ на счете в день зарплаты",
    desc: "Клиенты задержали оплату на 18 дней. На бумаге бизнес успешен, но платить сотрудникам нечем."
  },
  {
    num: "02",
    title: "Ловушка ст. 6.1 НК РФ",
    fact: "28 число — дедлайн ЕНП",
    reality: "Сдвиг списания на понедельник",
    desc: "Выходной переносит дату списания налогов. Обычные таблицы слепы к календарным пикам."
  },
  {
    num: "03",
    title: "Запоздалая реакция",
    fact: "24 часа до кризиса",
    reality: "Штрафы и блокировка счетов",
    desc: "Бизнес видит дыру накануне платежа, когда взять кредит или договориться с контрагентами уже поздно."
  }
];

s2Problems.forEach((p, i) => {
  const xPos = 0.8 + i * 2.85;
  slide2.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: xPos, y: 1.6, w: 2.65, h: 2.8,
    fill: { color: COLORS.cardBg },
    line: { color: COLORS.cardBorder, width: 1 },
    rectRadius: 0.08
  });
  slide2.addText(p.num, {
    x: xPos + 0.2, y: 1.75, w: 0.6, h: 0.3,
    fontSize: 14, fontFace: "Arial", bold: true, color: COLORS.primaryGreen
  });
  slide2.addText(p.title, {
    x: xPos + 0.2, y: 2.1, w: 2.25, h: 0.35,
    fontSize: 12, fontFace: "Arial", bold: true, color: COLORS.textDark
  });
  // Fact vs Reality
  slide2.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: xPos + 0.15, y: 2.5, w: 2.35, h: 0.75,
    fill: { color: COLORS.mintBg },
    rectRadius: 0.06
  });
  slide2.addText(p.fact, {
    x: xPos + 0.2, y: 2.55, w: 2.25, h: 0.32,
    fontSize: 11, fontFace: "Arial", bold: true, color: COLORS.darkGreen
  });
  slide2.addText(p.reality, {
    x: xPos + 0.2, y: 2.88, w: 2.25, h: 0.3,
    fontSize: 8.5, fontFace: "Arial", bold: true, color: COLORS.alertRed
  });
  slide2.addText(p.desc, {
    x: xPos + 0.2, y: 3.35, w: 2.25, h: 0.95,
    fontSize: 9, fontFace: "Arial", color: COLORS.textMuted
  });
});

// Airy Bottom Takeaway
slide2.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
  x: 0.8, y: 4.6, w: 8.35, h: 0.65,
  fill: { color: COLORS.cardBg },
  line: { color: COLORS.primaryGreen, width: 1 },
  rectRadius: 0.06
});
slide2.addText([
  { text: "ВЫВОД: ", options: { bold: true, color: COLORS.primaryGreen, fontSize: 10.5 } },
  { text: "Предпринимателю нужен не отчет о прошлых тратах, а автоматический радар будущих кассовых ям и готовое финансирование.", options: { color: COLORS.textDark, fontSize: 10 } }
], {
  x: 1.0, y: 4.6, w: 7.95, h: 0.65,
  fontFace: "Arial", valign: "middle"
});

slide2.addNotes("Почему Excel и выписки убивают бизнес? Первая слепая зона: иллюзия прибыли. Бизнес успешен в отчете, но клиенты задержали оплату, и платить зарплату нечем. Вторая: налоги РФ. Статья 6.1 НК переносит списание на понедельник, создавая скрытый пик. Третья: запоздалая реакция. Бизнес понимает проблему за 24 часа до факта. Вывод: нужен предиктивный радар с готовым решением.");

// ============================================================================
// SLIDE 3: Live Product & UI Design (1:00 - 1:40)
// ============================================================================
const slide3 = pptx.addSlide();
slide3.background = { color: COLORS.bgLight };
addCleanHeader(slide3, "ПРОДУКТ «ПОТОК»: РАБОЧИЙ ВЕБ-СЕРВИС ДЛЯ МСП", "Полнофункциональный MVP, созданный командой Patch_Note за хакатон");

// Left Column: Screenshot with clean border
slide3.addImage({
  path: SCREENSHOT_PATH,
  x: 0.8, y: 1.55, w: 5.5, h: 3.7
});

// Right Column: 3 Clean Value Cards
const s3Cards = [
  {
    badge: "РАДАР ЛИКВИДНОСТИ",
    title: "14 ноября: нехватка 188 131 ₽",
    desc: "Точный расчет риска кассового разрыва за 20 дней до наступления даты выплат."
  },
  {
    badge: "БЕСШОВНЫЙ ВВОД",
    title: "Импорт выписки 1С за 1 сек",
    desc: "Автоматическая очистка НДС, проверка 10-значных ИНН юрлиц ФНС и дедупликация."
  },
  {
    badge: "ПРЕДИКТИВНЫЙ ОВЕРДРАФТ",
    title: "Решение банка в 1 клик",
    desc: "Предодобренная кредитная линия на сумму разрыва прямо в интерфейсе графика."
  }
];

s3Cards.forEach((c, idx) => {
  const yPos = 1.55 + idx * 1.25;
  slide3.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: 6.5, y: yPos, w: 2.65, h: 1.15,
    fill: { color: COLORS.cardBg },
    line: { color: COLORS.cardBorder, width: 1 },
    rectRadius: 0.08
  });
  slide3.addText(c.badge, {
    x: 6.65, y: yPos + 0.1, w: 2.35, h: 0.22,
    fontSize: 8, fontFace: "Arial", bold: true, color: COLORS.primaryGreen
  });
  slide3.addText(c.title, {
    x: 6.65, y: yPos + 0.32, w: 2.35, h: 0.3,
    fontSize: 10.5, fontFace: "Arial", bold: true, color: COLORS.textDark
  });
  slide3.addText(c.desc, {
    x: 6.65, y: yPos + 0.62, w: 2.35, h: 0.45,
    fontSize: 8.5, fontFace: "Arial", color: COLORS.textMuted
  });
});

slide3.addNotes("Перед вами реальный экран сервиса «Поток», разработанный Владиславом Паршиным. В центре — радар: сплошная линия — история, пунктир — прогноз. Красная черта — нулевой рубеж. Справа система четко указывает: 14 ноября нехватка 188 тысяч рублей. Предприниматель видит проблему за 20 дней, а банк тут же предлагает решение в один клик.");

// ============================================================================
// SLIDE 4: Engineering & Math Core (1:40 - 2:10)
// ============================================================================
const slide4 = pptx.addSlide();
slide4.background = { color: COLORS.bgLight };
addCleanHeader(slide4, "ИНЖЕНЕРНОЕ ЯДРО: СТРОГАЯ МАТЕМАТИКА ВМЕСТО ГАДАНИЙ", "Математический аппарат Владимира Федорко: аналитика вместо наивных ML-моделей");

const s4Tech = [
  {
    num: "01",
    title: "First-Passage Time (FPT)",
    formula: "dB(t) = (mu - lambda)dt + sigma dW + J dN",
    desc: "Аналитическое решение SDE стохастического баланса с поправкой Миллса. Точная вероятность разрыва за доли секунды без Монте-Карло.",
    metric: "< 5 мс",
    metricLabel: "время аналитического расчета"
  },
  {
    num: "02",
    title: "Conformal Prediction",
    formula: "P( Y in C(X) ) >= 1 - alpha",
    desc: "Конечно-выборочные гарантии 90% покрытия коридора. Надежный доверительный интервал даже при сверхкороткой истории от 3 дней.",
    metric: "90%",
    metricLabel: "гарантированное покрытие риска"
  },
  {
    num: "03",
    title: "Инженерная надежность",
    formula: "Zero Regression | Full Safety Guards",
    desc: "Защита float64 от андерфлоу, балансировка Башелье с фактором 2, дедупликация выписок 1С и оптимистичные блокировки ревизий.",
    metric: "89 / 89",
    metricLabel: "тестов пройдено на аудите"
  }
];

s4Tech.forEach((t, i) => {
  const xPos = 0.8 + i * 2.85;
  slide4.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: xPos, y: 1.6, w: 2.65, h: 3.65,
    fill: { color: COLORS.cardBg },
    line: { color: COLORS.cardBorder, width: 1 },
    rectRadius: 0.08
  });
  slide4.addText(t.num, {
    x: xPos + 0.15, y: 1.75, w: 0.5, h: 0.3,
    fontSize: 15, fontFace: "Arial", bold: true, color: COLORS.primaryGreen
  });
  slide4.addText(t.title, {
    x: xPos + 0.65, y: 1.75, w: 1.85, h: 0.35,
    fontSize: 10.5, fontFace: "Arial", bold: true, color: COLORS.textDark
  });
  // Formula
  slide4.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: xPos + 0.15, y: 2.2, w: 2.35, h: 0.45,
    fill: { color: COLORS.mintBg },
    rectRadius: 0.05
  });
  slide4.addText(t.formula, {
    x: xPos + 0.2, y: 2.2, w: 2.25, h: 0.45,
    fontSize: 8, fontFace: "Courier New", bold: true, color: COLORS.darkGreen, align: "center", valign: "middle"
  });
  slide4.addText(t.desc, {
    x: xPos + 0.15, y: 2.75, w: 2.35, h: 1.3,
    fontSize: 9, fontFace: "Arial", color: COLORS.textMuted
  });
  // Metric Pill
  slide4.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: xPos + 0.15, y: 4.25, w: 2.35, h: 0.8,
    fill: { color: COLORS.tagLightBg },
    rectRadius: 0.06
  });
  slide4.addText(t.metric, {
    x: xPos + 0.2, y: 4.3, w: 2.25, h: 0.4,
    fontSize: 18, fontFace: "Arial", bold: true, color: COLORS.primaryGreen, align: "center"
  });
  slide4.addText(t.metricLabel, {
    x: xPos + 0.2, y: 4.7, w: 2.25, h: 0.25,
    fontSize: 8, fontFace: "Arial", color: COLORS.textMuted, align: "center"
  });
});

slide4.addNotes("Почему наше решение обходит наивные модели? Математическое ядро Владимира Федорко использует точное аналитическое решение First-Passage Time. Мы вычисляем вероятность банкротства за 5 миллисекунд без долгого Монте-Карло. Конформное прогнозирование гарантирует 90% покрытие даже на 3 днях истории, а надежность подтверждена 89 строгими автотестами.");

// ============================================================================
// SLIDE 5: Commercial Win-Win for Bank Case (2:10 - 2:40)
// ============================================================================
const slide5 = pptx.addSlide();
slide5.background = { color: COLORS.bgLight };
addCleanHeader(slide5, "ИНТЕГРАЦИЯ В КЕЙС БАНКА «ЦЕНТР-ИНВЕСТ»", "Как разработанный хакатонный сервис решает задачи банка и бизнеса");

const s5Grid = [
  {
    kpi: "x4",
    title: "Конверсия овердрафта",
    desc: "Таргетированное предложение кредита ровно в дату риска. Никакого спама — клиент берет финансирование в момент необходимости."
  },
  {
    kpi: "-18%",
    title: "Снижение дефолтов NPL",
    desc: "Ранняя идентификация кассового стресса за 30 дней защищает кредитный портфель банка от невозвратов."
  },
  {
    kpi: "0 ₽",
    title: "Затраты на привлечение",
    desc: "Бесплатный радар ликвидности работает как мощный якорный магнит РКО, удерживая компании в банке."
  },
  {
    kpi: "1 спринт",
    title: "Быстрое встраивание",
    desc: "Открытый REST API и готовый фронтенд-модуль легко интегрируются в существующий интернет-банк «Центр-инвест Бизнес»."
  }
];

s5Grid.forEach((g, idx) => {
  const col = idx % 2;
  const row = Math.floor(idx / 2);
  const xPos = 0.8 + col * 4.3;
  const yPos = 1.6 + row * 1.45;

  slide5.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: xPos, y: yPos, w: 4.05, h: 1.3,
    fill: { color: COLORS.cardBg },
    line: { color: COLORS.cardBorder, width: 1 },
    rectRadius: 0.08
  });
  // KPI Pill
  slide5.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x: xPos + 0.15, y: yPos + 0.15, w: 1.1, h: 0.45,
    fill: { color: COLORS.mintBg },
    rectRadius: 0.05
  });
  slide5.addText(g.kpi, {
    x: xPos + 0.15, y: yPos + 0.15, w: 1.1, h: 0.45,
    fontSize: 15, fontFace: "Arial", bold: true, color: COLORS.darkGreen, align: "center", valign: "middle"
  });
  slide5.addText(g.title, {
    x: xPos + 1.35, y: yPos + 0.15, w: 2.55, h: 0.35,
    fontSize: 11, fontFace: "Arial", bold: true, color: COLORS.textDark, valign: "top"
  });
  slide5.addText(g.desc, {
    x: xPos + 0.15, y: yPos + 0.68, w: 3.75, h: 0.52,
    fontSize: 8.8, fontFace: "Arial", color: COLORS.textMuted, valign: "top"
  });
});

// Airy Bottom Synergistic Formula Banner
slide5.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
  x: 0.8, y: 4.65, w: 8.35, h: 0.6,
  fill: { color: COLORS.cardBg },
  line: { color: COLORS.primaryGreen, width: 1 },
  rectRadius: 0.06
});
slide5.addText([
  { text: "СИНЕРГИЯ ХАКАТОНА И БАНКА: ", options: { bold: true, color: COLORS.primaryGreen, fontSize: 10 } },
  { text: "Банк получает готовый микросервис предиктивного кредитования, а малый бизнес Юга России — защиту от дефолта.", options: { color: COLORS.textDark, fontSize: 9.5 } }
], {
  x: 1.0, y: 4.65, w: 7.95, h: 0.6,
  fontFace: "Arial", valign: "middle"
});

slide5.addNotes("Как наш продукт решает задачу кейса? Мы создали предиктивную воронку кредитования. Банк заранее знает дату дефицита и предлагает овердрафт в момент максимальной готовности клиента. Конверсия выше в 4 раза, стоимость привлечения нулевая, а просрочка NPL падает на 18%. Решение встраивается в интернет-банк всего за один спринт.");

// ============================================================================
// SLIDE 6: Hackathon Results & Pilot Readiness (2:40 - 3:00)
// ============================================================================
const slide6 = pptx.addSlide();
slide6.background = { color: COLORS.bgLight };
addCleanHeader(slide6, "ИТОГИ ХАКАТОНА И ГОТОВНОСТЬ К ПИЛОТУ", "Команда Patch_Note создала законченный инженерный продукт за 48 часов");

// Left Column: Team Patch_Note
slide6.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
  x: 0.8, y: 1.6, w: 4.05, h: 2.7,
  fill: { color: COLORS.cardBg },
  line: { color: COLORS.cardBorder, width: 1 },
  rectRadius: 0.08
});
slide6.addText("КОМАНДА PATCH_NOTE", {
  x: 1.0, y: 1.75, w: 3.65, h: 0.3,
  fontSize: 11, fontFace: "Arial", bold: true, color: COLORS.primaryGreen
});
slide6.addText([
  { text: "Владимир Федорко\n", options: { bold: true, color: COLORS.textDark, fontSize: 12 } },
  { text: "Backend, Математическое ядро, FPT & Conformal\n", options: { bold: true, color: COLORS.darkGreen, fontSize: 9.5 } },
  { text: "Разработал математический аппарат, парсер выписок 1С, FastAPI бэкенд и 89 регрессионных тестов.\n\n", options: { color: COLORS.textMuted, fontSize: 9 } },
  { text: "Владислав Паршин\n", options: { bold: true, color: COLORS.textDark, fontSize: 12 } },
  { text: "Frontend, UI & UX Engineering, Дизайн-система\n", options: { bold: true, color: COLORS.darkGreen, fontSize: 9.5 } },
  { text: "Создал реактивный дашборд на React 18, визуализацию Recharts и адаптивную верстку по брендбуку.", options: { color: COLORS.textMuted, fontSize: 9 } }
], {
  x: 1.0, y: 2.1, w: 3.65, h: 2.05,
  fontFace: "Arial", valign: "top"
});

// Right Column: Hackathon Deliverables
slide6.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
  x: 5.1, y: 1.6, w: 4.05, h: 2.7,
  fill: { color: COLORS.cardBg },
  line: { color: COLORS.cardBorder, width: 1 },
  rectRadius: 0.08
});
slide6.addText("ЧТО СДЕЛАНО ЗА 48 ЧАСОВ ХАКАТОНА", {
  x: 5.3, y: 1.75, w: 3.65, h: 0.3,
  fontSize: 11, fontFace: "Arial", bold: true, color: COLORS.primaryGreen
});

const hackPoints = [
  "Полный рабочий стек: FastAPI + React 18 + PostgreSQL",
  "Синхронизация контрактов данных (TypeScript <-> Pydantic)",
  "89 автоматических тестов на граничные условия и сбои",
  "Парсер реальных выписок 1С с очисткой НДС и ИНН",
  "Готовность к интеграции в ДБО банка за 1 рабочий спринт"
];

hackPoints.forEach((pt, idx) => {
  slide6.addText("✓ " + pt, {
    x: 5.3, y: 2.15 + idx * 0.4, w: 3.65, h: 0.35,
    fontSize: 9.2, fontFace: "Arial", bold: idx === 4, color: idx === 4 ? COLORS.darkGreen : COLORS.textDark
  });
});

// Final Call to Action Banner
slide6.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
  x: 0.8, y: 4.45, w: 8.35, h: 0.8,
  fill: { color: COLORS.primaryGreen },
  rectRadius: 0.08
});
slide6.addText([
  { text: "ПРИГЛАШАЕМ ЖЮРИ К ЖИВОЙ ДЕМОНСТРАЦИИ СЕРВИСА «ПОТОК»!\n", options: { bold: true, color: "FFFFFF", fontSize: 11.5 } },
  { text: "Команда Patch_Note готова показать работу на реальной выписке 1С и ответить на вопросы.", options: { color: "FFFFFF", fontSize: 9.5 } }
], {
  x: 1.0, y: 4.45, w: 7.95, h: 0.8,
  fontFace: "Arial", align: "center", valign: "middle"
});

slide6.addNotes("Подводя итог хакатона: команда Patch_Note создала не просто презентацию, а законченную инженерную платформу. Стек современный, отказоустойчивый, математически строгий. «Поток» защищает малый бизнес от банкротства, а банку дает готовую воронку предиктивного кредитования. Мы уложились в 3 минуты и приглашаем вас к живой демонстрации сервиса на реальных данных 1С. Спасибо!");

// Save Presentation
const outputPath = path.resolve(__dirname, "../docs/presentation_patch_note_center_invest.pptx");
pptx.writeFile({ fileName: outputPath })
  .then(() => {
    console.log("Successfully compiled clean hackathon presentation to:", outputPath);
  })
  .catch(err => {
    console.error("Error writing PPTX:", err);
    process.exit(1);
  });
