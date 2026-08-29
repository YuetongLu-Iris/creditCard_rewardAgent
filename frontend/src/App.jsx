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
  const [walletData, setWalletData] = useState(null);
  const [selectedCard, setSelectedCard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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

  // ── Fetch dashboard data ───────────────────────────────────────────────────
  useEffect(() => {
    async function load() {
      try {
        const [r, t, w] = await Promise.all([
          axios.get(`${API}/report`),
          axios.get(`${API}/transactions`),
          axios.get(`${API}/wallet`),
        ]);
        setReport(r.data);
        setTxnData(t.data);
        setWalletData(w.data);
      } catch {
        setError("Could not load data. Make sure the FastAPI server is running and rewards_engine.py has been run.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

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

  async function refreshWallet() {
    try {
      const w = await axios.get(`${API}/wallet`);
      setWalletData(w.data);
    } catch {
      // non-critical — wallet just won't reflect the latest confirmation until next reload
    }
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
        ...(imageToSend
          ? { image_base64: imageToSend.base64, image_media_type: imageToSend.mediaType }
          : {}),
      }, { timeout: 110000 });
      setMessages((m) => [...m, {
        role: "agent",
        text: res.data.response,
        confirmOptions: res.data.confirm_card_options || null,
        confirmContext: text || "Photo recommendation",
      }]);
      setChatLoading(false);
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

  async function confirmCardUsage(cardName, context) {
    await refreshWalletAfter(
      axios.post(`${API}/confirm_card_usage`, {
        card_name: cardName,
        context: context || "",
        session_id: SESSION_ID,
      })
    );
  }

  async function refreshWalletAfter(promise) {
    try {
      await promise;
    } finally {
      refreshWallet();
    }
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

  const selectedCardData = walletData?.cards.find((c) => c.name === selectedCard) ?? null;

  const barData = report?.category_summaries
    ?.sort((a, b) => b.total_spent - a.total_spent)
    .map((s) => ({
      category: s.category.replace("_", " "),
      spent: parseFloat(s.total_spent.toFixed(2)),
      rewards: parseFloat(s.best_rewards.toFixed(2)),
    })) ?? [];

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
                      onConfirm={(card) => confirmCardUsage(card, m.confirmContext)}
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
            {(!walletData || walletData.cards.length === 0) && (
              <p className="status-msg">
                No cards on file yet — click "Add a Card" above, or tell the agent "I have a ___".
              </p>
            )}

            {walletData && walletData.cards.length > 0 && (
              <>
                <div className="wallet-grid">
                  {walletData.cards.map((c) => (
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
                        Recently confirmed for: {selectedCardData.actual_usage_recent.join(", ")}
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

                {/* Confirmed actual card usage */}
                {walletData && walletData.cards.some((c) => c.actual_usage_count > 0) && (
                  <div className="table-card">
                    <h2 className="chart-title">Confirmed Card Usage</h2>
                    <table className="rewards-table">
                      <thead>
                        <tr>
                          <th>Card</th>
                          <th>Times Confirmed</th>
                          <th>Most Recent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {walletData.cards
                          .filter((c) => c.actual_usage_count > 0)
                          .sort((a, b) => b.actual_usage_count - a.actual_usage_count)
                          .map((c) => (
                            <tr key={c.name}>
                              <td><span className="card-badge">{c.name}</span></td>
                              <td>{c.actual_usage_count}</td>
                              <td>{c.actual_usage_recent[c.actual_usage_recent.length - 1] || "—"}</td>
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
