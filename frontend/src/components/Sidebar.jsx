import { useState } from 'react'
import { BookOpen, Clock3, LogOut, Menu, MessageSquare, Plus, Settings, ShoppingBag, Trash2, X } from 'lucide-react'
import { NavLink, useNavigate } from 'react-router-dom'

const nav = [
  ['/knowledge', BookOpen, '知识库'], ['/history', Clock3, '历史'], ['/settings', Settings, '设置'],
]

export default function Sidebar({ systemOk, sessions, activeId, onSelect, onCreate, onDelete, user, onLogout }) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const select = id => { onSelect(id); navigate('/chat'); setOpen(false) }
  const create = async () => { await onCreate(); navigate('/chat'); setOpen(false) }

  const content = <div className="sidebar-inner">
    <div className="sidebar-brand"><span><ShoppingBag size={17} /></span><div>MERCHANT DESK<small>SHOPIFY OPERATIONS</small></div></div>
    <button className="new-chat" onClick={create}><Plus size={15} /> 新建对话</button>
    <div className="session-list" aria-label="最近对话">
      <p className="sidebar-label">最近对话</p>
      {!sessions.length && <p className="sidebar-empty">还没有对话</p>}
      {sessions.slice(0, 12).map(item => <div className={`session-item ${item.id === activeId ? 'active' : ''}`} key={item.id}>
        <button onClick={() => select(item.id)}><MessageSquare size={14} /><span>{item.title}</span></button>
        <button className="session-delete" aria-label={`删除 ${item.title}`} onClick={() => onDelete(item.id)}><Trash2 size={13} /></button>
      </div>)}
    </div>
    <nav className="side-nav">{nav.map(([to, Icon, label]) => <NavLink key={to} to={to} onClick={() => setOpen(false)}>
      <Icon size={16} />{label}
    </NavLink>)}</nav>
    <div className="sidebar-footer">
      <div className="user-chip"><span>{(user?.username || 'K').slice(0, 1).toUpperCase()}</span><div>{user?.username}<small><i className={systemOk ? 'online' : ''} />{systemOk ? '应用服务正常' : '检查应用服务'}</small></div></div>
      <button onClick={onLogout} aria-label="退出登录"><LogOut size={16} /></button>
    </div>
  </div>

  return <>
    <aside className="sidebar desktop-sidebar">{content}</aside>
    <header className="mobile-header"><button onClick={() => setOpen(true)} aria-label="打开导航"><Menu /></button><b>MERCHANT DESK</b></header>
    {open && <div className="mobile-drawer"><aside className="sidebar"><button className="drawer-close" onClick={() => setOpen(false)}><X /></button>{content}</aside><button className="drawer-backdrop" onClick={() => setOpen(false)} aria-label="关闭导航" /></div>}
  </>
}
