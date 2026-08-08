"use client";

import { classNames } from "@/lib/utils";

export function Table({
  head,
  children,
  empty,
  className,
}: {
  head: React.ReactNode;
  children: React.ReactNode;
  empty?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={classNames("overflow-x-auto", className)}>
      <table className="w-full min-w-[560px] text-sm">
        <thead>
          <tr className="border-b border-line">{head}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {empty}
    </div>
  );
}

export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={classNames("table-head px-4 py-3", className)}>{children}</th>;
}

export function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={classNames("px-4 py-3 text-ink", className)}>{children}</td>;
}

export function Tr({ children, onClick, className }: { children: React.ReactNode; onClick?: () => void; className?: string }) {
  return (
    <tr
      onClick={onClick}
      className={classNames("border-b border-line last:border-0 hover:bg-canvas/60", onClick && "cursor-pointer", className)}
    >
      {children}
    </tr>
  );
}
