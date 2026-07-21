import { NavLink, Outlet } from "react-router-dom";

const links = [
  { to: "/", label: "Overview", end: true },
  { to: "/data", label: "Data Capture" },
  { to: "/runs", label: "Runs" },
  { to: "/factors", label: "Survivors" },
  { to: "/jobs", label: "Jobs" },
];

export function Layout() {
  return (
    <div className="layout">
      <aside className="nav">
        <div className="brand">
          <div className="brand-mark">QRA</div>
          <div className="brand-title">Monitor</div>
          <div className="brand-sub">Capture · experiments · survivors</div>
        </div>
        <nav className="nav-links">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="nav-foot">poll · actions enabled</div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
