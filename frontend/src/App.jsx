import { useState, useEffect, useRef } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
} from "recharts";
import axios from "axios";
import "./App.css";
//import ReacMarkdown from "react-markdown";
//import { default as ReactMarkdown } from "react-markdown";
import {marked} from "marked"
//const API = "http://localhost:8000";
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
// function ChatMessage({ role, text }) {
//   return (
//     <div className={`message ${role}`}>
//       <div className="message-bubble">
//         {text.split("\n").map((line, i) => (
//           <span key={i}>{line}{i < text.split("\n").length - 1 && <br />}</span>
//         ))}
//       </div>
//     </div>
//   );
// }


function ChatMessage({ role, text }) {
  if (!text) return null;
  return (
    <div className={`message ${role}`}>
      <div
        className="message-bubble"
        dangerouslySetInnerHTML={
          role === "agent"
            ? { __html: marked(text) }
            : undefined
        }
      >
        {role !== "agent" ? text : undefined}
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [report, setReport] = useState(null);
  const [txnData, setTxnData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Chat state
  const [messages, setMessages] = useState([
    {
      role: "agent",
      text: "Hi! I'm your rewards agent. Ask me which card to use, how much you spent on dining, or how to maximise your cashback.",
    },
  ]);
  const [input, setInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const bottomRef = useRef(null);

  // ── Fetch dashboard data ───────────────────────────────────────────────────
  useEffect(() => {
    async function load() {
      try {
        const [r, t] = await Promise.all([
          axios.get(`${API}/report`),
          axios.get(`${API}/transactions`),
        ]);
        setReport(r.data);
        setTxnData(t.data);
      } catch (e) {
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

  // ── Send chat message ──────────────────────────────────────────────────────
  async function sendMessage() {
    const text = input.trim();
    if (!text || chatLoading) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setChatLoading(true);

    try {
      const res = await axios.post(`${API}/chat`, {
        message: text,
        session_id: SESSION_ID,
      });
      setMessages((m) => [...m, { role: "agent", text: res.data.response }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "agent", text: "Sorry, something went wrong. Is the backend running?" },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
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
            <button
              className={`nav-btn ${tab === "dashboard" ? "active" : ""}`}
              onClick={() => setTab("dashboard")}
            >
              Dashboard
            </button>
            <button
              className={`nav-btn ${tab === "chat" ? "active" : ""}`}
              onClick={() => setTab("chat")}
            >
              Chat
            </button>
          </nav>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="main">

        {/* ── Dashboard Tab ── */}
        {tab === "dashboard" && (
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
              </>
            )}
          </div>
        )}

        {/* ── Chat Tab ── */}
        {tab === "chat" && (
          <div className="chat-container">
            <div className="chat-messages">
              {messages.map((m, i) => (
                <ChatMessage key={i} role={m.role} text={m.text} />
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

            <div className="chat-input-row">
              <textarea
                className="chat-input"
                rows={1}
                placeholder="Ask about your spending or rewards…"
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

            <p className="chat-hint">
              Try: "Which card for Whole Foods?" · "Show my rewards report" · "Compare Amex Gold vs Chase Sapphire"
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
