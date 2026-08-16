"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const MODES = [
  { href: "/search/agent", label: "AI 搜题", caption: "用教学语言描述需求" },
  { href: "/search", label: "高级筛选", caption: "按章节、题型与质量筛选" },
] as const;

function isActive(href: string, pathname: string): boolean {
  if (href === "/search") return pathname === "/search";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SearchModeTabs() {
  const pathname = usePathname();
  return (
    <nav className="search-mode-tabs" aria-label="搜题方式">
      {MODES.map((mode) => {
        const active = isActive(mode.href, pathname);
        return (
          <Link
            key={mode.href}
            href={mode.href}
            className={active ? "active" : ""}
            aria-current={active ? "page" : undefined}
          >
            <strong>{mode.label}</strong>
            <span>{mode.caption}</span>
          </Link>
        );
      })}
    </nav>
  );
}