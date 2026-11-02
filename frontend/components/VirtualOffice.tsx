"use client";

import { cn } from "@/lib/utils";
import { ChevronRight, ChevronLeft, ChevronUp, ChevronDown, MoreHorizontal, RefreshCw, Settings, Zap, BarChart3, Users, Brain, MessageSquare, Bell, Settings, Search, Filter, ChevronDown, ChevronUp, Download, Upload, Plus, Trash2, Edit, Eye, Copy, Share, ExternalLink, RotateCcw, AlertTriangle, CheckCircle, XCircle, HelpCircle, Info, AlertCircle, Star, Flag, Bookmark, Tag, Link, Hash, Key, Lock, Unlock, Shield, Eye, EyeOff, Volume2, VolumeX, Mic, MicOff, Camera, CameraOff, Wifi, WifiOff, Battery, BatteryLow, Settings, Cpu, HardDrive, Monitor, Smartphone, Tablet, Laptop, Server, Database, Cloud, Globe, Network, Shield, Lock, Key, Unlock, Heart, Star, Flag, Bookmark, Tag, Link, Hash, Key, Lock, Unlock, Shield, Eye, EyeOff, Volume2, VolumeX, Mic, MicOff, Camera, CameraOff, Wifi, WifiOff, Battery, BatteryLow, Settings, Cpu, HardDrive, Monitor, Smartphone, Tablet, Laptop, Server, Database, Cloud, Globe, Network, Shield, Lock, Key, Unlock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";
import { classNames } from "@/lib/utils";

interface VirtualOfficeProps {
  employees: Array<{
    id: string;
    name: string;
    email: string;
    avatar?: string;
    role: string;
    department: string;
    status: "available" | "busy" | "meeting" | "dnd" | "away" | "offline";
    location?: string;
    currentRoom?: string;
  }>;
  rooms: Array<{
    id: string;
    name: string;
    type: "meeting" | "focus" | "social" | "presentation" | "private";
    capacity: number;
    currentOccupants: number;
    occupants: string[];
    position: { x: number; y: number };
    size: { width: number; height: number };
  }>;
  currentUser: {
    id: string;
    name: string;
    avatar?: string;
    status: string;
  };
  onRoomEnter?: (roomId: string) => void;
  onUserClick?: (userId: string) => void;
  onRoomClick?: (roomId: string) => void;
  className?: string;
}

export function VirtualOffice({
  employees,
  rooms,
  currentUser,
  onRoomEnter,
  onUserClick,
  onRoomClick,
  className,
}: VirtualOfficeProps) {
  const [viewMode, setViewMode] = useState<"2d" | "3d" | "isometric">("isometric");
  const [zoom, setZoom] = useState(1);
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null);
  const [showUserPanel, setShowUserPanel] = useState(false);
  const [showRoomPanel, setShowRoomPanel] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  const handleCanvasClick = (e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // Check if clicked on a room
    const clickedRoom = rooms.find(room => {
      const roomX = room.position.x * zoomLevel + panOffset.x;
      const roomY = room.position.y * zoomLevel + panOffset.y;
      const roomWidth = room.size.width * zoomLevel;
      const roomHeight = room.size.height * zoomLevel;
      
      return (
        x >= roomX &&
        x <= roomX + roomWidth &&
        y >= roomY &&
        y <= roomY + roomHeight
      );
    });
    
    if (clickedRoom) {
      setSelectedRoom(clickedRoom.id);
      setShowRoomPanel(true);
    } else {
      setSelectedRoom(null);
      setShowRoomPanel(false);
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setZoomLevel(prev => Math.max(0.5, Math.min(2, prev + delta)));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
      e.preventDefault();
      setIsDragging(true);
      setDragStart({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      const dx = e.clientX - dragStart.x;
      const dy = e.clientY - dragStart.y;
      setPanOffset(prev => ({
        x: prev.x + dx,
        y: prev.y + dy,
      }));
      setDragStart({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const resetView = () => {
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "available": return "success";
      case "busy": return "danger";
      case "meeting": return "warning";
      case "dnd": return "danger";
      case "away": return "warning";
      case "offline": return "default";
      default: return "default";
    }
  };

  const getRoomColor = (type: string) => {
    switch (type) {
      case "meeting": return "brand";
      case "focus": return "success";
      case "social": return "warning";
      case "presentation": return "brand";
      case "private": return "muted";
      default: return "default";
    }
  };

  return (
    <div className={cn("relative flex-1 overflow-hidden bg-canvas", className)}>
      {/* Header Controls */}
      <div className="absolute top-0 left-0 right-0 z-10 p-3 flex items-center justify-between bg-canvas/80 backdrop-blur-sm border-b border-line">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-ink">Virtual Office</h2>
          <Badge variant="outline" className="ml-2 capitalize">{viewMode}</Badge>
        </div>
        
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setZoomLevel(prev => Math.max(0.5, prev - 0.1))}
              aria-label="Zoom out"
            >
              <Minus className="h-4 w-4" />
            </Button>
            <span className="text-sm text-muted w-10 text-center">{Math.round(zoomLevel * 100)}%</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setZoomLevel(prev => Math.min(2, prev + 0.1))}
              aria-label="Zoom in"
            >
              <Plus className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={resetView}
              aria-label="Reset view"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          </div>
          
          <div className="flex items-center gap-2 ml-4">
            <Button
              variant={viewMode === "2d" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("2d")}
            >
              <Square className="h-4 w-4" />
              <span className="hidden sm:inline">2D</span>
            </Button>
            <Button
              variant={viewMode === "isometric" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("isometric")}
            >
              <Cube className="h-4 w-4" />
              <span className="hidden sm:inline">3D</span>
            </Button>
            <Button
              variant={viewMode === "3d" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("3d")}
            >
              <Box className="h-4 w-4" />
              <span className="hidden sm:inline">Perspective</span>
            </Button>
          </div>
        </div>

        {/* Main Office Canvas */}
        <div
          ref={containerRef}
          className="relative flex-1 overflow-hidden"
          onClick={handleCanvasClick}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="relative overflow-hidden"
          style={{ transform: `scale(${zoomLevel}) translate(${panOffset.x}px, ${panOffset.y}px)`, transformOrigin: "center center" }}
        >
          {/* Grid Background */}
          <div className="absolute inset-0 bg-grid opacity-20" style={{ transform: `scale(${1/zoomLevel})` }} />
          
          {/* Rooms */}
          {rooms.map((room) => (
            <Room
              key={room.id}
              room={room}
              zoom={zoomLevel}
              panOffset={panOffset}
              selected={selectedRoom === room.id}
              onClick={() => {
                setSelectedRoom(room.id);
                setShowRoomPanel(true);
                onRoomClick?.(room.id);
              }}
              onEnter={() => onRoomEnter?.(room.id)}
            />
          ))}
          
          {/* Employee Avatars */}
          {employees.map((employee) => (
            <EmployeeAvatar
              key={employee.id}
              employee={employee}
              zoom={zoomLevel}
              panOffset={panOffset}
              selected={selectedUser === employee.id}
              onClick={() => {
                setSelectedUser(employee.id);
                setShowUserPanel(true);
              }}
            />
          ))}
          
          {/* Grid Lines */}
          <div className="absolute inset-0 bg-grid opacity-20 pointer-events-none" />
        </div>

        {/* Mini-map */}
        <div className="absolute bottom-4 right-4 z-20 w-48 h-32 bg-surface/90 backdrop-blur-lg rounded-lg border border-line shadow-lg p-2">
          <div className="w-full h-full bg-canvas/50 rounded border border-line relative overflow-hidden">
            {rooms.map((room) => (
              <div
                key={room.id}
                className="absolute"
                style={{
                  left: `${(room.position.x / 1000) * 100}%`,
                  top: `${(room.position.y / 1000) * 100}%`,
                  width: `${(room.size.width / 1000) * 100}%`,
                  height: `${(room.size.height / 1000) * 100}%`,
                }}
              >
                <div 
                  className="absolute inset-0 rounded"
                  style={{ 
                    backgroundColor: getRoomColorHex(room.type),
                    opacity: 0.7 
                  }}
                />
              </div>
            ))}
            {employees.map((employee) => (
              <div
                key={employee.id}
                className="absolute w-2 h-2 rounded-full"
                style={{
                  left: `${(employee.currentRoom ? rooms.find(r => r.id === employee.currentRoom)?.position.x : 500) / 1000 * 100}%`,
                  top: `${(employee.currentRoom ? rooms.find(r => r.id === employee.currentRoom)?.position.y : 500) / 1000 * 100}%`,
                  backgroundColor: getStatusColorHex(employee.status),
                  border: "2px solid white",
                }
              </div>
            ))}
          </div>
        </div>

        {/* User Panel */}
        {showUserPanel && selectedUser && (
          <UserPanel
            user={employees.find(u => u.id === selectedUser)!}
            onClose={() => { setShowUserPanel(false); setSelectedUser(null); }}
            onAction={(action) => onUserClick?.(selectedUser!)}
          />
        )}

        {/* Room Panel */}
        {showRoomPanel && selectedRoom && (
          <RoomPanel
            room={rooms.find(r => r.id === selectedRoom)!}
            onClose={() => { setShowRoomPanel(false); setSelectedRoom(null); }}
            onEnter={onRoomEnter}
          />
        )}

        {/* Status Bar */}
        <div className="absolute bottom-0 left-0 right-0 z-10 p-2 flex items-center justify-between bg-canvas/80 backdrop-blur-sm border-t border-line">
          <div className="flex items-center gap-4 text-sm text-muted">
            <span>{employees.filter(e => e.status === "available").length} available</span>
            <span>|</span>
            <span>{employees.filter(e => e.status === "meeting").length} in meetings</span>
            <span>|</span>
            <span>{rooms.filter(r => r.currentOccupants > 0).length} active rooms</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted">Zoom: {Math.round(zoomLevel * 100)}%</span>
            <Button variant="ghost" size="sm" onClick={resetView}>
              <RotateCcw className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </div>
    );
  );
}

// Room Component
interface RoomProps {
  room: {
    id: string;
    name: string;
    type: "meeting" | "focus" | "social" | "presentation" | "private";
    capacity: number;
    currentOccupants: number;
    occupants: string[];
    position: { x: number; y: number };
    size: { width: number; height: number };
  };
  zoom: number;
  panOffset: { x: number; y: number };
  selected: boolean;
  onClick: () => void;
  onEnter?: (roomId: string) => void;
}

function Room({ room, zoom, panOffset, selected, onClick, onEnter }: RoomProps) {
  const x = room.position.x * zoom + (window.innerWidth / 2) + 0; // simplified
  const y = room.position.y * zoom + (window.innerHeight / 2) + 0; // simplified
  const width = room.size.width;
  const height = room.size.height;

  const roomColors = {
    meeting: "bg-brand/20 border-brand/30",
    focus: "bg-success/20 border-success/30",
    social: "bg-warning/20 border-warning/30",
    presentation: "bg-brand/20 border-brand/30",
    private: "bg-muted/20 border-muted/30",
  };

  return (
    <div
      className={cn(
        "absolute rounded-lg border-2 transition-all duration-200 cursor-pointer",
        "hover:shadow-lg hover:scale-[1.02]",
        selected && "ring-2 ring-brand",
        roomColors[room.type] || "bg-surface/50 border-line"
      )}
      style={{
        left: `calc(50% + ${room.position.x}px)`,
        top: `calc(50% + ${room.position.y}px)`,
        width: room.size.width,
        height: room.size.height,
        transform: `translate(-50%, -50%)`,
      }}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      onDoubleClick={onEnter}
      onMouseEnter={(e) => {
        e.stopPropagation();
      }}
    >
      <div className="absolute inset-0 flex flex-col items-center justify-center p-2">
        <div className="flex items-center justify-between w-full px-2 pb-1">
          <span className="text-xs font-medium text-ink truncate">{room.name}</span>
          <span className="text-xs text-muted">{room.currentOccupants}/{room.capacity}</span>
        </div>
        <div className="flex-1 flex items-center justify-center">
          {room.currentOccupants > 0 && (
            <div className="flex -space-x-1">
              {Array.from({ length: Math.min(5, room.currentOccupants) }).map((_, i) => (
                <div key={i} className="w-5 h-5 rounded-full bg-brand/20 border-2 border-surface ring-1 ring-surface flex-shrink-0" />
              ))}
              {5 < room.currentOccupants && (
                <div className="w-5 h-5 rounded-full bg-brand/20 border-2 border-surface flex-shrink-0 flex items-center justify-center text-[10px] text-brand font-medium">
                  +{5}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Employee Avatar Component
interface EmployeeAvatarProps {
  employee: {
    id: string;
    name: string;
    email: string;
    avatar?: string;
    role: string;
    department: string;
    status: "available" | "busy" | "meeting" | "dnd" | "away" | "offline";
    location?: string;
    currentRoom?: string;
  };
  zoom: number;
  panOffset: { x: number; y: number };
  selected: boolean;
  onClick: () => void;
}

function EmployeeAvatar({ employee, zoom, panOffset, selected, onClick }: EmployeeAvatarProps) {
  // Simplified positioning - in real implementation, this would be based on actual position
  const statusColors = {
    available: "bg-success",
    busy: "bg-danger",
    meeting: "bg-warning",
    dnd: "bg-danger",
    away: "bg-warning",
    offline: "bg-muted",
  };

  const getInitials = (name: string) => {
    return name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2);
  };

  return (
    <div
      className={cn(
        "absolute flex flex-col items-center gap-1 cursor-pointer transition-all duration-200",
        "hover:scale-110 z-10"
      )}
      style={{
        left: `calc(50% + ${Math.random() * 800 - 400}px)`, // Simplified random positioning
        top: `calc(50% + ${Math.random() * 600 - 300}px)`,
        transform: "translate(-50%, -50%)",
      }}
      onClick={(e) => {
        e.stopPropagation();
        // onClick();
      }}
    >
      <div className={cn(
        "relative flex flex-col items-center gap-1 transition-all duration-200",
        "hover:scale-110"
      )}>
        <div className="relative">
          <div className={cn(
            "w-8 h-8 rounded-full bg-brand-soft text-brand font-medium flex items-center justify-center text-sm font-medium ring-2 ring-surface",
            "border-2 border-surface shadow-md"
          )}>
            {getInitials("John Doe")}
          </div>
          <div className={cn(
            "absolute bottom-0 right-0 w-3 h-3 rounded-full border-2 border-surface",
            "bg-success" // Simplified - would use employee.status
          )} />
        </div>
        <span className="text-xs font-medium text-ink truncate max-w-[80px] text-center">
          John Doe
        </span>
        <div className="flex items-center gap-1 text-[10px] text-muted">
          <span className="w-1.5 h-1.5 rounded-full bg-success" />
          <span className="truncate max-w-[60px]">Available</span>
        </div>
      </div>
    </div>
  );
}

// User Panel
interface UserPanelProps {
  user: {
    id: string;
    name: string;
    email: string;
    avatar?: string;
    role: string;
    department: string;
    status: string;
    location?: string;
    currentRoom?: string;
  };
  onClose: () => void;
  onAction: (action: string) => void;
}

function UserPanel({ user, onClose, onAction }: UserPanelProps) {
  return (
    <div className="fixed right-4 top-20 z-50 w-72 bg-surface rounded-xl border border-line shadow-lg p-4 animate-slideInRight">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-brand-soft text-brand flex items-center justify-center text-sm font-medium">
            {user.name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2)}
          </div>
          <div>
            <p className="font-medium text-ink">{user.name}</p>
            <p className="text-xs text-muted">{user.email}</p>
          </div>
        </div>
        <button onClick={onClose} className="p-1 text-muted hover:text-ink hover:bg-canvas rounded-lg transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted w-24">Role</span>
          <span className="font-medium text-ink">{user.role}</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted w-24">Department</span>
          <span className="text-ink">{user.department}</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted w-24">Status</span>
          <Badge variant="success">{user.status}</Badge>
        </div>
        {user.currentRoom && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted w-24">Current Room</span>
            <span className="font-medium text-ink">{user.currentRoom}</span>
          </div>
        )}
        <div className="pt-2 border-t border-line flex gap-2">
          <Button variant="outline" size="sm" className="flex-1" onClick={() => {}}>
            <MessageSquare className="h-4 w-4 mr-1" /> Message
          </Button>
          <Button variant="outline" size="sm" className="flex-1">
            <Video className="h-4 w-4 mr-1" /> Call
          </Button>
        </div>
      </div>
    </div>
  );
}

// Room Panel
interface RoomPanelProps {
  room: {
    id: string;
    name: string;
    type: "meeting" | "focus" | "social" | "presentation" | "private";
    capacity: number;
    currentOccupants: number;
    occupants: string[];
    position: { x: number; y: number };
    size: { width: number; height: number };
  };
  onClose: () => void;
  onEnter?: (roomId: string) => void;
}

function RoomPanel({ room, onClose, onEnter }: RoomPanelProps) {
  const roomColors = {
    meeting: "bg-brand/10 text-brand border-brand/20",
    focus: "bg-success/10 text-success border-success/20",
    social: "bg-warning/10 text-warning border-warning/20",
    presentation: "bg-brand/10 text-brand border-brand/20",
    private: "bg-muted/10 text-muted border-muted/20",
  };

  const typeLabels = {
    meeting: "Meeting Room",
    focus: "Focus Room",
    social: "Social Space",
    presentation: "Presentation Room",
    private: "Private Office",
  };

  return (
    <div className="fixed right-4 top-20 z-50 w-80 bg-surface rounded-xl border border-line shadow-lg p-4 animate-slideInRight">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className={cn("inline-flex items-center gap-2 px-2 py-1 rounded-full text-xs font-medium", 
            type === "meeting" ? "bg-brand/10 text-brand border border-brand/20" :
            type === "focus" ? "bg-success/10 text-success border-success/20" :
            type === "social" ? "bg-warning/10 text-warning border-warning/20" :
            type === "presentation" ? "bg-brand/10 text-brand border-brand/20" :
            "bg-muted/10 text-muted border-muted/20"
          )}>
            {typeLabels[type]}
          </div>
        </div>
        <button onClick={onClose} className="p-1 text-muted hover:text-ink hover:bg-canvas rounded-lg transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium text-ink">{room.name}</p>
            <p className="text-sm text-muted">{room.currentOccupants}/{room.capacity} occupants</p>
          </div>
          <Badge variant="outline">{room.type}</Badge>
        </div>
        
        {room.occupants.length > 0 && (
          <div>
            <p className="text-sm font-medium text-muted mb-2">Occupants</p>
            <div className="flex flex-wrap gap-2">
              {room.occupants.slice(0, 5).map((occupant, i) => (
                <Badge key={i} variant="outline" className="text-xs">{occupant}</Badge>
              ))}
              {room.occupants.length > 5 && (
                <Badge variant="outline" className="text-xs">+{room.occupants.length - 5} more</Badge>
              )}
            </div>
          </div>
        )}
        
        <div className="pt-3 border-t border-line flex gap-2">
          <Button variant="secondary" className="flex-1" onClick={() => onEnter?.(room.id)}>
            <LogIn className="h-4 w-4 mr-1" /> Enter Room
          </Button>
          <Button variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// Helper functions
function getInitials(name: string): string {
  return name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2);
}

function getStatusColorHex(status: string): string {
  switch (status) {
    case "available": return "#10B981";
    case "busy": return "#EF4444";
    case "meeting": return "#F59E0B";
    case "dnd": return "#EF4444";
    case "away": return "#F59E0B";
    case "offline": return "#9CA3AF";
    default: return "#9CA3AF";
  }
}

function getRoomColorHex(type: string): string {
  switch (type) {
    case "meeting": return "#6366F1";
    case "focus": return "#10B981";
    case "social": return "#F59E0B";
    case "presentation": return "#6366F1";
    case "private": return "#9CA3AF";
    default: return "#9CA3AF";
  }
}

function getStatusColorHex(status: string): string {
  switch (status) {
    case "available": return "#10B981";
    case "busy": return "#EF4444";
    case "meeting": return "#F59E0B";
    case "dnd": return "#EF4444";
    case "away": return "#F59E0B";
    case "offline": return "#9CA3AF";
    default: return "#9CA3AF";
  }
}

export { VirtualOffice };

// Export types
export type { VirtualOfficeProps, RoomProps, EmployeeAvatarProps, UserPanelProps, RoomPanelProps };