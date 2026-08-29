import { useState, useEffect, useRef } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
} from "recharts";
import axios from "axios";
import "./App.css";
import {marked} from "marked"
const API = "https://creditcard-rewardagent.onrender.com";
const SESSION_ID = "user-session-1";

// The user's wallet (owned cards + confirmed usage) lives in the browser —
// Render's free tier has no persistent disk, so anything written
// server-side gets wiped on the next deploy. localStorage survives that.
const LS_KEYS = { cards: "rewardsAgent.ownedCards", usage: "rewardsAgent.usageLog" };

function loadLocal(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function saveLocal(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable (private mode, quota) — non-critical, just won't persist
  }
}

function computeHighlight(card) {
  if (card.rates && card.rates.length > 0) {
    const best = card.rates.reduce((a, b) => (b.multiplier > a.multiplier ? b : a));
    return `${best.multiplier}x ${best.category}`;
  }
  return `${card.base_rate}x on everything`;
}

// ── Colours for charts ────────────────────────────────────────────────────────
const CHART_COLORS = [
  "#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd",
  "#818cf8", "#4f46e5", "#7c3aed", "#5b21b6",
];

// ── Small components ──────────────────────────────────────────────────────────
// Configure marked to support tables
marked.setOptions({
  gfm: true,
});

const formatCategory = (cat) =>
  cat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

function StatCard({ label, value, sub }) {
  return (
    <div className="stat-card">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {sub && <p className="stat-sub">{sub}</p>}
    </div>
  );
}

function ChatMessage({ role, text, imageUrl }) {
  if (!text && !imageUrl) return null;
  return (
    <div className={`message ${role}`}>
      <div className="message-bubble">
        {imageUrl && <img src={imageUrl} alt="Attachment" className="message-image" />}
        {text && role === "agent" && (
          <div dangerouslySetInnerHTML={{ __html: marked(text) }} />
        )}
        {text && role !== "agent" && <span>{text}</span>}
      </div>
    </div>
  );
}

// Chips shown after a card recommendation: "which card did you actually use?"
function ConfirmCardPrompt({ options, onConfirm }) {
  const [confirmed, setConfirmed] = useState(null);
  const [showOther, setShowOther] = useState(false);
  const [otherText, setOtherText] = useState("");

  if (confirmed) {
    return <p className="confirm-done">✓ Logged: {confirmed}</p>;
  }

  function pick(cardName) {
    setConfirmed(cardName);
    onConfirm(cardName);
  }

  function saveOther() {
    const name = otherText.trim();
    if (!name) return;
    pick(name);
  }

  return (
    <div className="confirm-card-row">
      <p className="confirm-card-label">Which card did you use?</p>
      <div className="confirm-card-chips">
        {options.filter((o) => o !== "Other").map((opt) => (
          <button key={opt} className="confirm-chip" onClick={() => pick(opt)}>
            {opt}
          </button>
        ))}
        <button className="confirm-chip other" onClick={() => setShowOther(true)}>
          Other
        </button>
      </div>
      {showOther && (
        <div className="confirm-other-row">
          <input
            className="confirm-other-input"
            placeholder="Card name"
            autoFocus
            value={otherText}
            onChange={(e) => setOtherText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && saveOther()}
          />
          <button className="confirm-other-save" onClick={saveOther}>Save</button>
        </div>
      )}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [report, setReport] = useState(null);
  const [txnData, setTxnData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Wallet — owned cards + confirmed usage are local (see LS_KEYS comment above).
  const [ownedCards, setOwnedCards] = useState(() => loadLocal(LS_KEYS.cards, []));
  const [usageLog, setUsageLog] = useState(() => loadLocal(LS_KEYS.usage, []));
  const [walletEnrichment, setWalletEnrichment] = useState({}); // name -> {usage, highlight}
  const [selectedCard, setSelectedCard] = useState(null);

  // Chat state
  const [messages, setMessages] = useState([
    {
      role: "agent",
      text: "Hi! Drop a photo of a receipt or storefront and I'll tell you which card to use — or just ask.",
    },
  ]);
  const [input, setInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);

  // ── Persist wallet state locally ───────────────────────────────────────────
  useEffect(() => saveLocal(LS_KEYS.cards, ownedCards), [ownedCards]);
  useEffect(() => saveLocal(LS_KEYS.usage, usageLog), [usageLog]);

  // ── Fetch dashboard data (shared, server-side) ─────────────────────────────
  useEffect(() => {
    async function load() {
      try {
        const [r, t] = await Promise.all([
          axios.get(`${API}/report`),
          axios.get(`${API}/transactions`),
        ]);
        setReport(r.data);
        setTxnData(t.data);
      } catch {
        setError("Could not load data. Make sure the FastAPI server is running and rewards_engine.py has been run.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // ── Enrich owned cards with rewards-relevance from the backend ────────────
  // (catalog details + how much each card earns against real spending —
  // this needs server-side data the browser doesn't have; usage/ownership
  // itself doesn't, so it isn't sent here.)
  useEffect(() => {
    // Nothing to enrich — harmless to leave any stale entries in
    // walletEnrichment, since walletCards only ever reads names that are
    // still in ownedCards.
    if (ownedCards.length === 0) return;

    axios.post(`${API}/wallet`, { card_names: ownedCards.map((c) => c.name) })
      .then((res) => {
        const map = {};
        for (const c of res.data.cards) map[c.name] = c;
        setWalletEnrichment(map);
      })
      .catch(() => {
        // non-critical — cards still render from local data, just without
        // the rewards-relevance table until this succeeds
      });
  }, [ownedCards]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const keepAlive = setInterval(() => {
      axios.get(`${API}/`).catch(() => {});  // silent ping
    }, 10 * 60 * 1000);  // every 10 minutes

    return () => clearInterval(keepAlive);
  }, []);

  // ── Apply what the backend says happened to a card ─────────────────────────
  function applyWalletAction(action) {
    if (!action) return;
    if (action.type === "add") {
      setOwnedCards((prev) => {
        if (prev.some((c) => c.name === action.card.name)) return prev;
        return [...prev, { ...action.card, added_date: new Date().toISOString().slice(0, 10) }];
      });
    } else if (action.type === "remove") {
      const query = action.card_name.toLowerCase();
      setOwnedCards((prev) =>
        prev.filter((c) => !(query.includes(c.name.toLowerCase()) || c.name.toLowerCase().includes(query)))
      );
    }
  }

  // Confirming which card was used is a pure local write — no backend
  // round-trip, so it can never be lost to a redeploy or go out of sync.
  function confirmCardUsage(cardName, pendingPurchase) {
    setUsageLog((prev) => [...prev, {
      card_name: cardName,
      merchant_or_category: pendingPurchase?.merchant_or_category || null,
      amount: pendingPurchase?.amount || null,
      date: new Date().toISOString().slice(0, 10),
    }]);
  }

  // ── Send chat message (text and/or image) ─────────────────────────────────
  // Some requests (new-card research, adding an unfamiliar card) do a live
  // web search and can legitimately take 30-60+ seconds — timeout is sized
  // for that, not just a quick recommendation. A failure could still be a
  // cold free-tier backend waking up, so retry once with an honest message.
  async function sendPayload(text, imageToSend, attempt = 1) {
    if (attempt === 1) {
      if ((!text && !imageToSend) || chatLoading) return;
      setMessages((m) => [...m, { role: "user", text, imageUrl: imageToSend?.previewUrl }]);
      setInput("");
      setChatLoading(true);
    }

    try {
      const res = await axios.post(`${API}/chat`, {
        message: text,
        session_id: SESSION_ID,
        owned_cards: ownedCards.map((c) => c.name),
        ...(imageToSend
          ? { image_base64: imageToSend.base64, image_media_type: imageToSend.mediaType }
          : {}),
      }, { timeout: 110000 });
      setMessages((m) => [...m, {
        role: "agent",
        text: res.data.response,
        confirmOptions: res.data.confirm_card_options || null,
        pendingPurchase: res.data.pending_purchase || null,
      }]);
      setChatLoading(false);
      applyWalletAction(res.data.wallet_action);
    } catch {
      if (attempt === 1) {
        setMessages((m) => [...m, {
          role: "agent",
          text: "⏳ That took too long — could be a sleeping free-tier server or a slow search. Retrying…",
        }]);
        setTimeout(() => sendPayload(text, imageToSend, 2), 6000);
        return;
      }
      setMessages((m) => [
        ...m,
        { role: "agent", text: "Sorry, still no response. Please try again in a moment." },
      ]);
      setChatLoading(false);
    }
  }

  function sendMessage() {
    sendPayload(input.trim(), null);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  // Drop the image straight in — no preview/confirm step, that's the whole point.
  function handleImageSelect(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result; // "data:image/png;base64,...."
      const base64 = dataUrl.split(",")[1];
      const image = { previewUrl: dataUrl, base64, mediaType: file.type || "image/jpeg" };
      const caption = input.trim();
      sendPayload(caption, image);
    };
    reader.readAsDataURL(file);
  }

  function askBestCardToOpen() {
    sendPayload("What's the best card to open right now?", null);
  }

  function startAddCard() {
    const prefill = "I have ";
    setInput(prefill);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(prefill.length, prefill.length);
      }
    });
  }

  // ── Dashboard helpers ──────────────────────────────────────────────────────
  const pieData = txnData?.category_breakdown?.map((c) => ({
    name: formatCategory(c.category),
    value: c.total,
  })) ?? [];

  const barData = report?.category_summaries
    ?.sort((a, b) => b.total_spent - a.total_spent)
    .map((s) => ({
      category: s.category.replace("_", " "),
      spent: parseFloat(s.total_spent.toFixed(2)),
      rewards: parseFloat(s.best_rewards.toFixed(2)),
    })) ?? [];

  // ── Wallet helpers (merge local ownership + local usage + server enrichment) ─
  const walletCards = ownedCards.map((c) => {
    const enrichment = walletEnrichment[c.name];
    const cardUsage = usageLog.filter((u) => u.card_name === c.name);
    return {
      ...c,
      highlight: enrichment?.highlight ?? computeHighlight(c),
      usage: enrichment?.usage ?? [],
      actual_usage_count: cardUsage.length,
      actual_usage_total: cardUsage.reduce((sum, u) => sum + (u.amount || 0), 0),
      actual_usage_recent: cardUsage.slice(-3).map((u) => u.merchant_or_category).filter(Boolean),
    };
  });
  const selectedCardData = walletCards.find((c) => c.name === selectedCard) ?? null;

  // ── Dashboard: confirmed usage summary, grouped from the local log ────────
  const usageByCard = {};
  for (const u of usageLog) {
    if (!usageByCard[u.card_name]) usageByCard[u.card_name] = { count: 0, total: 0, recent: null };
    usageByCard[u.card_name].count += 1;
    usageByCard[u.card_name].total += u.amount || 0;
    usageByCard[u.card_name].recent = u.merchant_or_category || usageByCard[u.card_name].recent;
  }
  const usageSummary = Object.entries(usageByCard)
    .map(([name, s]) => ({ name, ...s }))
    .sort((a, b) => b.count - a.count);

  function scrollTo(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="app">

      {/* ── Header ── */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-icon">💳</span>
            <span className="logo-text">RewardsAgent</span>
          </div>
          <nav className="nav">
            <button className="nav-btn" onClick={() => scrollTo("wallet-section")}>My Cards</button>
            <button className="nav-btn" onClick={() => scrollTo("dashboard-section")}>Dashboard</button>
          </nav>
        </div>
      </header>

      {/* ── Main: single scrolling page ── */}
      <main className="main">

        {/* ── Chat hero — the core interaction, always front and center ── */}
        <section className="chat-hero">
          <div className="chat-container compact">
            <div className="chat-messages">
              {messages.map((m, i) => (
                <div key={i}>
                  <ChatMessage role={m.role} text={m.text} imageUrl={m.imageUrl} />
                  {m.confirmOptions && (
                    <ConfirmCardPrompt
                      options={m.confirmOptions}
                      onConfirm={(card) => confirmCardUsage(card, m.pendingPurchase)}
                    />
                  )}
                </div>
              ))}
              {chatLoading && (
                <div className="message agent">
                  <div className="message-bubble typing">
                    <span /><span /><span />
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <div className="quick-actions">
              <button className="quick-action-btn" onClick={askBestCardToOpen} disabled={chatLoading}>
                🔥 Best Card to Open Now
              </button>
              <button className="quick-action-btn" onClick={startAddCard} disabled={chatLoading}>
                ➕ Add a Card
              </button>
            </div>

            <div className="chat-input-row">
              <input
                type="file"
                accept="image/*"
                ref={fileInputRef}
                onChange={handleImageSelect}
                style={{ display: "none" }}
              />
              <button
                type="button"
                className="attach-btn"
                onClick={() => fileInputRef.current?.click()}
                disabled={chatLoading}
                title="Drop a photo — receipt, storefront, or card — for an instant recommendation"
              >
                📎
              </button>
              <textarea
                ref={textareaRef}
                className="chat-input"
                rows={1}
                placeholder="Ask, or just attach a photo…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
              />
              <button
                className="send-btn"
                onClick={sendMessage}
                disabled={chatLoading || !input.trim()}
              >
                Send
              </button>
            </div>
          </div>
        </section>

        {/* ── My Cards ── */}
        <section id="wallet-section" className="page-section">
          <h2 className="section-title">My Cards</h2>
          <div className="wallet">
            {walletCards.length === 0 && (
              <p className="status-msg">
                No cards on file yet — click "Add a Card" above, or tell the agent "I have a ___".
              </p>
            )}

            {walletCards.length > 0 && (
              <>
                <div className="wallet-grid">
                  {walletCards.map((c) => (
                    <button
                      key={c.name}
                      className={`wallet-tile ${selectedCard === c.name ? "active" : ""}`}
                      onClick={() => setSelectedCard(selectedCard === c.name ? null : c.name)}
                    >
                      <span className="wallet-tile-name">{c.name}</span>
                      <span className="wallet-tile-highlight">{c.highlight}</span>
                      <span className="wallet-tile-fee">
                        ${c.annual_fee.toFixed(0)}/yr
                        {c.actual_usage_count > 0 && ` · used ${c.actual_usage_count}x`}
                      </span>
                    </button>
                  ))}
                </div>

                {selectedCardData && (
                  <div className="wallet-detail">
                    <h3 className="chart-title">{selectedCardData.name}</h3>

                    <ul className="wallet-bullets">
                      <li>Annual fee: ${selectedCardData.annual_fee.toFixed(0)}</li>
                      <li>Base rate: {selectedCardData.base_rate}x on everything else</li>
                      {selectedCardData.rates.map((r, i) => (
                        <li key={i}>{r.category}: {r.multiplier}x — {r.description}</li>
                      ))}
                    </ul>

                    {selectedCardData.official_url && (
                      <a
                        href={selectedCardData.official_url}
                        target="_blank"
                        rel="noreferrer"
                        className="wallet-official-link"
                      >
                        Official card details ↗
                      </a>
                    )}

                    {selectedCardData.actual_usage_recent.length > 0 && (
                      <p className="wallet-recent-usage">
                        Confirmed {selectedCardData.actual_usage_count}x
                        {selectedCardData.actual_usage_total > 0 &&
                          ` (~$${selectedCardData.actual_usage_total.toFixed(2)} total)`}
                        {" — recently for: "}
                        {selectedCardData.actual_usage_recent.join(", ")}
                      </p>
                    )}

                    {selectedCardData.usage.length > 0 && (
                      <table className="rewards-table">
                        <thead>
                          <tr>
                            <th>Category</th>
                            <th>Your Spend</th>
                            <th>Rewards w/ this Card</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedCardData.usage.map((u, i) => (
                            <tr key={i}>
                              <td>{formatCategory(u.category)}</td>
                              <td>${u.spent.toFixed(2)}</td>
                              <td className="rewards-cell">
                                ${u.rewards_if_used.toFixed(2)}
                                {u.is_best_card && <span className="card-badge wallet-best-badge">Best</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        {/* ── Dashboard ── */}
        <section id="dashboard-section" className="page-section">
          <h2 className="section-title">Dashboard</h2>
          <div className="dashboard">
            {loading && <p className="status-msg">Loading your data…</p>}
            {error && <p className="status-msg error">{error}</p>}

            {!loading && !error && report && txnData && (
              <>
                {/* Stat cards */}
                <div className="stat-row">
                  <StatCard
                    label="Total Spent"
                    value={`$${txnData.total_spent.toFixed(2)}`}
                    sub={`${txnData.total_transactions} transactions`}
                  />
                  <StatCard
                    label="Max Rewards Available"
                    value={`$${report.total_best_rewards.toFixed(2)}`}
                    sub="with optimal card mix"
                  />
                  <StatCard
                    label="Categories Tracked"
                    value={report.category_summaries.length}
                    sub="spending categories"
                  />
                </div>

                {/* Charts row */}
                <div className="charts-row">

                  {/* Pie – spending by category */}
                  <div className="chart-card">
                    <h2 className="chart-title">Spending by Category</h2>
                    <ResponsiveContainer width="100%" height={260}>
                      <PieChart>
                        <Pie
                          data={pieData}
                          cx="50%"
                          cy="45%"
                          innerRadius={55}
                          outerRadius={85}
                          paddingAngle={3}
                          dataKey="value"
                        >
                          {pieData.map((_, i) => (
                            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v) => `$${v.toFixed(2)}`} />
                        <Legend
                          layout="horizontal"
                          verticalAlign="bottom"
                          align="center"
                          wrapperStyle={{ fontSize: "11px", paddingTop: "12px", lineHeight: "20px" }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Bar – spent vs rewards per category */}
                  <div className="chart-card">
                    <h2 className="chart-title">Spend vs Potential Rewards</h2>
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={barData} margin={{ left: 0, right: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                        <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} />
                        <Tooltip formatter={(v) => `$${v.toFixed(2)}`} />
                        <Legend />
                        <Bar dataKey="spent" fill="#6366f1" name="Spent" />
                        <Bar dataKey="rewards" fill="#a78bfa" name="Rewards" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Best card per category table */}
                <div className="table-card">
                  <h2 className="chart-title">Best Card by Category</h2>
                  <table className="rewards-table">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Total Spent</th>
                        <th>Best Card</th>
                        <th>Rewards Earned</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.category_summaries
                        .sort((a, b) => b.total_spent - a.total_spent)
                        .map((s, i) => (
                          <tr key={i}>
                            <td>{formatCategory(s.category)}</td>
                            <td>${s.total_spent.toFixed(2)}</td>
                            <td><span className="card-badge">{s.best_card}</span></td>
                            <td className="rewards-cell">${s.best_rewards.toFixed(2)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>

                {/* Confirmed actual card usage (local log) */}
                {usageSummary.length > 0 && (
                  <div className="table-card">
                    <h2 className="chart-title">Confirmed Card Usage</h2>
                    <table className="rewards-table">
                      <thead>
                        <tr>
                          <th>Card</th>
                          <th>Times Confirmed</th>
                          <th>Total Confirmed Spend</th>
                          <th>Most Recent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usageSummary.map((s) => (
                          <tr key={s.name}>
                            <td><span className="card-badge">{s.name}</span></td>
                            <td>{s.count}</td>
                            <td className="rewards-cell">{s.total > 0 ? `$${s.total.toFixed(2)}` : "—"}</td>
                            <td>{s.recent || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
