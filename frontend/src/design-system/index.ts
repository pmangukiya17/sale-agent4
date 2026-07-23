// M8.1 — Design System Foundation barrel export. Every later milestone
// imports primitives from "../design-system" (or a relative equivalent),
// never by reaching into an individual file directly - this is what
// keeps the import surface stable as more primitives are added in later
// milestones (Select, Table, Tooltip, etc. per Design Bible Section 4.6).
export { Button } from "./Button";
export type { ButtonProps } from "./Button";
export { Badge } from "./Badge";
export type { BadgeProps, BadgeTone } from "./Badge";
export { Card, ambientGlowStyle, activeGlowStyle, activeGlowOverlayClassName } from "./Card";
export type { CardProps, AccentColor } from "./Card";
export { Input } from "./Input";
export { StatusIndicator } from "./StatusIndicator";
export type { StatusIndicatorProps, StatusKind } from "./StatusIndicator";
export { Tabs } from "./Tabs";
export type { TabItem } from "./Tabs";
// M8.7 Phase D — filling Section 4.6's remaining component catalog gaps.
export { Select } from "./Select";
export { Table } from "./Table";
export type { TableColumn, TableProps } from "./Table";
export { Modal } from "./Modal";
export type { ModalProps } from "./Modal";
// M8.17 — Global Delete System's shared confirmation surface.
export { ConfirmDialog } from "./ConfirmDialog";
export type { ConfirmDialogProps } from "./ConfirmDialog";
export { ToastProvider, useToast } from "./Toast";
export type { ToastOptions, ToastTone } from "./Toast";
export { Tooltip } from "./Tooltip";
export type { TooltipProps } from "./Tooltip";
// Relocated from dashboard/ in M8.7 Phase E - see its own docstring.
export { PlaceholderNotice } from "./PlaceholderNotice";
export type { PlaceholderKind } from "./PlaceholderNotice";
export { cn } from "./cn";
export * from "./tokens";
