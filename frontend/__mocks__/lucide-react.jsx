const icons = [
  "Home",
  "LayoutGrid",
  "ListTodo",
  "Sun",
  "Building2",
  "Sparkles",
  "Brain",
  "Users",
  "FolderKanban",
  "Target",
  "TrendingUp",
  "FileText",
  "CheckCircle2",
  "AlertTriangle",
  "Plus",
  "Search",
  "Zap",
  "DollarSign",
  "HeartPulse",
  "ArrowRight",
  "ChevronDown",
  "ChevronUp",
  "Loader2",
  "Bell",
  "Clock",
  "BarChart2",
  "Shield",
  "Briefcase",
  "Settings",
  "Menu",
  "X",
  "RefreshCw",
  "Activity",
  "UserPlus",
  "Cloud",
  "Key",
  "MessageSquare",
  "Ticket",
  "Truck",
  "Check",
  "RotateCw",
  "AlertCircle",
  "CheckCircle2",
  "Users",
  "FileText",
  "AlertTriangle",
  "Users",
  "DollarSign",
  "HeartPulse",
  "Zap",
  "Users",
  "Building2",
  "Sparkles",
  "Target",
];

const mockComponents = {};
icons.forEach((icon) => {
  mockComponents[icon] = ({ className, ...props }) => (
    <svg
      className={className}
      {...props}
      data-testid={`icon-${icon.toLowerCase()}`}
    />
  );
});

module.exports = mockComponents;
