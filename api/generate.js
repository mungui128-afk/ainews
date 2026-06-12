/** Vercel serverless — Gemini 보고서 생성 */

const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-2.5-flash-lite';

function parseRss(xml) {
  const items = [];
  const blocks = xml.match(/<item>[\s\S]*?<\/item>/gi) || [];
  for (const block of blocks.slice(0, 15)) {
    const title = (block.match(/<title>([\s\S]*?)<\/title>/) || [])[1]?.replace(/<!\[CDATA\[|\]\]>/g, '').trim() || '';
    const link = (block.match(/<link>([\s\S]*?)<\/link>/) || [])[1]?.trim() || '';
    const pubDate = (block.match(/<pubDate>([\s\S]*?)<\/pubDate>/) || [])[1]?.trim() || '';
    const desc = (block.match(/<description>([\s\S]*?)<\/description>/) || [])[1]?.replace(/<[^>]+>/g, '').trim() || '';
    const source = (block.match(/<source[^>]*>([\s\S]*?)<\/source>/) || [])[1]?.trim() || title.split(' - ').pop() || '';
    if (!title) continue;
    items.push({ title, link, desc, source, published: pubDate });
  }
  return items;
}

async function fetchNews(keyword) {
  const q = encodeURIComponent(`${keyword} when:7d`);
  const url = `https://news.google.com/rss/search?q=${q}&hl=ko&gl=KR&ceid=KR:ko`;
  const res = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
  if (!res.ok) throw new Error('뉴스 RSS 수집 실패');
  const xml = await res.text();
  return parseRss(xml);
}

async function callGemini(prompt) {
  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) throw new Error('GEMINI_API_KEY 환경변수가 설정되지 않았습니다.');

  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${apiKey}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.4, responseMimeType: 'application/json' },
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Gemini API 오류: ${err.slice(0, 200)}`);
  }
  const data = await res.json();
  return data.candidates[0].content.parts[0].text;
}

function fallbackReport(keyword, articles) {
  const top5 = articles.slice(0, 5);
  return {
    executive_summary: `최근 7일간 '${keyword}' 관련 뉴스 ${articles.length}건을 분석했습니다.`,
    top_issues: top5.map((a, i) => ({
      rank: i + 1,
      title: a.title,
      key_content: (a.desc || a.title).slice(0, 300),
      why_important: `'${keyword}' 분야 최근 동향 파악에 중요합니다.`,
      source: a.source,
      link: a.link,
    })),
  };
}

async function generateReport(keyword, articles) {
  const newsText = articles.slice(0, 12).map((a, i) =>
    `${i + 1}. [${a.source}] ${a.title}\n   요약: ${(a.desc || '').slice(0, 200)}\n   URL: ${a.link}`
  ).join('\n');

  const prompt = `당신은 뉴스 분석 전문가입니다. JSON만 출력하세요.\n\n키워드: ${keyword}\n\n뉴스:\n${newsText}\n\n형식:\n{"executive_summary":"핵심요약 3~4문장","top_issues":[{"rank":1,"title":"","key_content":"","why_important":"","source":"","link":""}]}\n\ntop_issues 5개.`;

  try {
    const raw = await callGemini(prompt);
    const data = JSON.parse(raw);
    const issues = (data.top_issues || []).slice(0, 5).map((issue, i) => ({ ...issue, rank: i + 1 }));
    return { executive_summary: data.executive_summary || '', top_issues: issues };
  } catch {
    return fallbackReport(keyword, articles);
  }
}

function nowKST() {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
}

function formatDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}년 ${m}월 ${day}일`;
}

function formatTime(d) {
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map(n => String(n).padStart(2, '0')).join(':');
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ success: false, error: 'POST만 허용' });

  try {
    const { keyword } = req.body || {};
    if (!keyword?.trim()) return res.status(400).json({ success: false, error: '키워드를 입력해 주세요.' });

    const articles = await fetchNews(keyword.trim());
    if (!articles.length) {
      return res.status(404).json({ success: false, error: `'${keyword}' 관련 뉴스를 찾지 못했습니다.` });
    }

    const report = await generateReport(keyword.trim(), articles);
    const created = nowKST();

    return res.status(200).json({
      success: true,
      keyword: keyword.trim(),
      article_count: articles.length,
      created_date: formatDate(created),
      created_time: formatTime(created),
      executive_summary: report.executive_summary,
      top_issues: report.top_issues,
      articles,
    });
  } catch (e) {
    return res.status(500).json({ success: false, error: e.message || '서버 오류' });
  }
};
