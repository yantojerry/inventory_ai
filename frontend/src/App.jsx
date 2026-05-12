import React, { useEffect, useMemo, useRef, useState } from 'react';
import { API, apiFetch, clearAuthToken, setAuthToken } from './services/api.js';

const NAV = [
  { id: 'dashboard', label: 'Dashboard', group: 'Main', icon: 'grid', showAddItem: true },
  { id: 'alerts', label: 'Alerts', group: 'Main', icon: 'bell', showAddItem: false },
  { id: 'items', label: 'Items', group: 'Inventory', icon: 'box', showAddItem: true },
  { id: 'transactions', label: 'Transactions', group: 'Inventory', icon: 'cash', manageOnly: true, showAddItem: true },
  { id: 'ai', label: 'AI Engine', group: 'Intelligence', icon: 'spark', showAddItem: false },
  { id: 'industries', label: 'Industries', group: 'Admin', icon: 'layers', superOnly: true, showAddItem: false },
  { id: 'admin', label: 'Users', group: 'Admin', icon: 'user', superOnly: true, showAddItem: false },
];

const TITLES = {
  dashboard: 'Dashboard',
  alerts: 'Active Alerts',
  items: 'Inventory Items',
  transactions: 'Transaction History',
  ai: 'AI Engine',
  industries: 'Industry Setup',
  admin: 'User Management',
};

const DEFAULT_INDUSTRY_TASKS = [
  'inventory_management',
  'sales_transactions',
  'stock_alerts',
  'ai_recommendations',
  'report_generation',
];

const emptyItem = {
  sku: '',
  name: '',
  industry: '',
  stock_quantity: '',
  unit_cost: '',
  expiry_date: '',
  attributes: {
    category: '',
    supplier: '',
    location: '',
    lead_time_days: '',
    batch_number: '',
    asset_tag: '',
    warranty_expiry: '',
  },
};

const emptyUser = {
  username: '',
  full_name: '',
  password: '',
  role: 'user',
  industries: [],
  is_active: true,
};

const emptyIndustry = {
  key: '',
  display_name: '',
  description: '',
  task_keys: DEFAULT_INDUSTRY_TASKS,
  track_expiry: true,
  track_batch: false,
  dynamic_attributes: 'category=general\nsupplier=default_supplier\nlocation=',
  minimum_stock: 10,
  expiry_warning_days: 30,
  lead_time_days: 7,
  safety_stock_multiplier: 1.25,
  minimum_order_quantity: 5,
};

function normalizeInventory(rows) {
  return rows.map((row) => ({
    ...row.item,
    ai: row.ai,
    workflowAlertCount: row.workflow_alert_count,
  }));
}

function displayIndustry(industry) {
  const names = {
    retail: 'Retail',
    healthcare: 'Healthcare',
    manufacturing: 'Manufacturing',
    it: 'IT Assets',
  };
  return names[industry] || titleCase(industry || '');
}

function titleCase(value) {
  return String(value || '')
    .replaceAll('_', ' ')
    .split(' ')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function industryDisplayName(key, industryMap = {}) {
  return industryMap[key]?.display_name || displayIndustry(key);
}

function attributesToText(attributes = {}) {
  return Object.entries(attributes)
    .map(([key, value]) => `${key}=${value ?? ''}`)
    .join('\n');
}

function parseAttributes(value) {
  const attributes = {};
  String(value || '')
    .split(/\r?\n|,/)
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const [rawKey, ...rest] = line.split('=');
      const key = rawKey.trim().toLowerCase().replaceAll(' ', '_').replaceAll('-', '_');
      if (!key) return;
      const rawValue = rest.join('=').trim();
      attributes[key] = rawValue === '' ? null : rawValue;
    });
  return attributes;
}

function fieldsFromAttributes(attributes) {
  return ['sku', 'name', ...Object.keys(attributes)].filter((value, index, array) => array.indexOf(value) === index);
}

function compareText(left, right) {
  return String(left ?? '').localeCompare(String(right ?? ''), undefined, {
    numeric: true,
    sensitivity: 'base',
  });
}

function compareNumber(left, right) {
  return Number(left ?? 0) - Number(right ?? 0);
}

function sortItems(items, sortConfig) {
  const direction = sortConfig.direction === 'desc' ? -1 : 1;
  return [...items].sort((left, right) => {
    if (sortConfig.key === 'name') return compareText(left.name, right.name) * direction;
    if (sortConfig.key === 'unit_cost') return compareNumber(left.unit_cost, right.unit_cost) * direction;
    if (sortConfig.key === 'stock_quantity') return compareNumber(left.stock_quantity, right.stock_quantity) * direction;
    return compareText(left.sku, right.sku) * direction;
  });
}

function industryBadge(industry) {
  return {
    retail: 'badge-blue',
    healthcare: 'badge-purple',
    manufacturing: 'badge-amber',
    it: 'badge-green',
  }[industry] || 'badge-blue';
}

function roleLabel(role) {
  return {
    super_admin: 'Super Admin',
    industry_admin: 'Industry Admin',
    user: 'User',
  }[role] || role;
}

function canManageInventory(user) {
  return ['super_admin', 'industry_admin'].includes(user?.role);
}

function isSuperAdmin(user) {
  return user?.role === 'super_admin';
}

function formatDate(value) {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

function statusFor(item) {
  const alerts = item.ai?.workflow?.alerts || [];
  const expiryRisk = item.ai?.expiry_risk?.risk_level;
  if (item.stock_quantity === 0) return { label: 'OUT OF STOCK', className: 'badge-red' };
  if (Number(item.stock_quantity) < 5) return { label: 'LOW STOCK', className: 'badge-amber' };
  if (alerts.some((alert) => alert.type === 'minimum_stock')) return { label: 'LOW STOCK', className: 'badge-amber' };
  if (expiryRisk === 'critical') return { label: 'EXPIRY RISK', className: 'badge-red' };
  if (['warning', 'watch'].includes(expiryRisk)) return { label: 'EXPIRY WATCH', className: 'badge-amber' };
  return { label: 'OK', className: 'badge-green' };
}

function quantityClass(item) {
  const status = statusFor(item);
  if (status.className === 'badge-red') return 'badge-red';
  if (status.className === 'badge-amber') return 'badge-amber';
  return 'badge-green';
}

function flattenAlerts(items) {
  const alerts = [];
  for (const item of items) {
    if (Number(item.stock_quantity) === 0) {
      alerts.push({
        sku: item.sku,
        name: item.name,
        industry: item.industry,
        title: 'OUT OF STOCK',
        detail: 'Stock reached zero and needs immediate review.',
        severity: 'critical',
      });
    } else if (Number(item.stock_quantity) < 5) {
      alerts.push({
        sku: item.sku,
        name: item.name,
        industry: item.industry,
        title: 'LOW STOCK',
        detail: `Only ${item.stock_quantity} unit(s) remain in stock.`,
        severity: 'warning',
      });
    }
    for (const alert of item.ai?.workflow?.alerts || []) {
      alerts.push({
        sku: item.sku,
        name: item.name,
        industry: item.industry,
        title: alert.type.replaceAll('_', ' ').toUpperCase(),
        detail: alert.message,
        severity: alert.severity === 'critical' ? 'critical' : 'warning',
      });
    }
    for (const anomaly of item.ai?.anomaly_detection?.anomalies || []) {
      alerts.push({
        sku: item.sku,
        name: item.name,
        industry: item.industry,
        title: 'SALES ANOMALY',
        detail: `${anomaly.date}: actual ${anomaly.actual_quantity}, expected ${anomaly.expected_quantity}`,
        severity: 'info',
      });
    }
  }
  return alerts;
}

function Icon({ type }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: '2', viewBox: '0 0 24 24' };
  if (type === 'grid') return <svg {...common}><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></svg>;
  if (type === 'bell') return <svg {...common}><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></svg>;
  if (type === 'box') return <svg {...common}><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /></svg>;
  if (type === 'cash') return <svg {...common}><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" /></svg>;
  if (type === 'user') return <svg {...common}><path d="M20 21a8 8 0 0 0-16 0" /><circle cx="12" cy="7" r="4" /></svg>;
  if (type === 'layers') return <svg {...common}><path d="M12 2 2 7l10 5 10-5-10-5Z" /><path d="m2 17 10 5 10-5" /><path d="m2 12 10 5 10-5" /></svg>;
  if (type === 'chevron-left') return <svg {...common}><polyline points="15 18 9 12 15 6" /></svg>;
  if (type === 'chevron-right') return <svg {...common}><polyline points="9 18 15 12 9 6" /></svg>;
  if (type === 'chevron-down') return <svg {...common}><polyline points="6 9 12 15 18 9" /></svg>;
  if (type === 'chevron-up') return <svg {...common}><polyline points="18 15 12 9 6 15" /></svg>;
  if (type === 'plus') return <svg {...common}><path d="M12 5v14M5 12h14" /></svg>;
  if (type === 'check') return <svg {...common}><polyline points="20 6 9 17 4 12" /></svg>;
  return <svg {...common}><circle cx="12" cy="12" r="3" /><path d="M19.07 4.93l-1.41 1.41M5.34 18.66l-1.41 1.41M20 12h-2M4 12H2M19.07 19.07l-1.41-1.41M5.34 5.34L3.93 3.93M12 20v2M12 2v2" /></svg>;
}

function App() {
  const [section, setSection] = useState('dashboard');
  const [authReady, setAuthReady] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [loginForm, setLoginForm] = useState({ username: 'superadmin', password: 'admin123' });
  const [industries, setIndustries] = useState({});
  const [industryRecords, setIndustryRecords] = useState([]);
  const [taskModules, setTaskModules] = useState([]);
  const [industry, setIndustry] = useState('');
  const [items, setItems] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('connecting');
  const [toast, setToast] = useState(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [loginSubmitting, setLoginSubmitting] = useState(false);
  const [itemSubmitting, setItemSubmitting] = useState(false);
  const [txSubmitting, setTxSubmitting] = useState(false);
  const [userSubmitting, setUserSubmitting] = useState(false);
  const [industrySubmitting, setIndustrySubmitting] = useState(false);
  const [itemModal, setItemModal] = useState(false);
  const [txModal, setTxModal] = useState(false);
  const [userModal, setUserModal] = useState(false);
  const [industryModal, setIndustryModal] = useState(false);
  const [editingSku, setEditingSku] = useState(null);
  const [editingUserId, setEditingUserId] = useState(null);
  const [editingIndustryKey, setEditingIndustryKey] = useState(null);
  const [form, setForm] = useState(emptyItem);
  const [txForm, setTxForm] = useState({ sku: '', change: '', reason: '' });
  const [userForm, setUserForm] = useState(emptyUser);
  const [industryForm, setIndustryForm] = useState({ ...emptyIndustry, task_keys: [...DEFAULT_INDUSTRY_TASKS] });
  const [itemSort, setItemSort] = useState({ key: 'sku', direction: 'asc' });
  const [aiSku, setAiSku] = useState('');
  const [aiResults, setAiResults] = useState({});
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', content: 'Tell me the industry you are adding and I will recommend the task modules and baseline settings.' },
  ]);
  const [chatInput, setChatInput] = useState('Which modules should I enable?');
  const [setupRecommendation, setSetupRecommendation] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      if (typeof window === 'undefined') return false;
      return window.localStorage.getItem('inventory_sidebar_collapsed') === 'true';
    } catch {
      return false;
    }
  });
  const [pendingScrollTarget, setPendingScrollTarget] = useState(null);
  const contentRef = useRef(null);
  const canManage = canManageInventory(currentUser);
  const isSuper = isSuperAdmin(currentUser);

  const visibleNav = useMemo(() => NAV.filter((item) => {
    if (item.superOnly && !isSuper) return false;
    if (item.manageOnly && !canManage) return false;
    return true;
  }), [canManage, isSuper]);
  const activeNavItem = useMemo(() => visibleNav.find((item) => item.id === section) || null, [section, visibleNav]);
  const showAddItemButton = Boolean(canManage && activeNavItem?.showAddItem);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => setToast(null), 3000);
  };

  const loadData = async () => {
    setDataLoading(true);
    const params = new URLSearchParams();
    if (industry) params.set('industry', industry);
    if (search.trim()) params.set('search', search.trim());
    try {
      const [industryPayload, inventoryPayload, txPayload] = await Promise.all([
        apiFetch('/industries'),
        apiFetch(`/inventory?${params.toString()}`),
        apiFetch('/transactions?days=120'),
      ]);
      setIndustries(industryPayload.industries);
      setIndustryRecords(industryPayload.industry_records || []);
      setTaskModules(industryPayload.task_modules || []);
      setItems(normalizeInventory(inventoryPayload.items));
      setTransactions(txPayload.transactions);
    } finally {
      setDataLoading(false);
    }
  };

  const loadUsers = async () => {
    if (!isSuperAdmin(currentUser)) return;
    const payload = await apiFetch('/users');
    setUsers(payload.users);
  };

  const checkHealth = async () => {
    try {
      await apiFetch('/health');
      setStatus('online');
    } catch {
      setStatus('offline');
    }
  };

  useEffect(() => {
    const restoreSession = async () => {
      try {
        await checkHealth();
        const payload = await apiFetch('/auth/me');
        setCurrentUser(payload.user);
      } catch {
        clearAuthToken();
      } finally {
        setAuthReady(true);
      }
    };
    restoreSession();
    const timer = window.setInterval(checkHealth, 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!currentUser) return;
    loadData().catch((error) => showToast(error.message, 'error'));
    if (isSuperAdmin(currentUser)) loadUsers().catch((error) => showToast(error.message, 'error'));
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser) return;
    loadData().catch((error) => showToast(error.message, 'error'));
  }, [industry]);

  useEffect(() => {
    if (!visibleNav.some((item) => item.id === section)) {
      setSection('dashboard');
    }
  }, [section, visibleNav]);

  useEffect(() => {
    try {
      window.localStorage.setItem('inventory_sidebar_collapsed', sidebarCollapsed ? 'true' : 'false');
    } catch {
      // Ignore storage failures and keep the UI working.
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (pendingScrollTarget === 'industries' && section === 'industries') {
      const timer = window.setTimeout(() => {
        document.getElementById('industries-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        setPendingScrollTarget(null);
      }, 0);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [pendingScrollTarget, section]);

  const filteredItems = useMemo(() => {
    if (!search.trim()) return items;
    const needle = search.trim().toLowerCase();
    return items.filter((item) =>
      item.sku.toLowerCase().includes(needle) ||
      item.name.toLowerCase().includes(needle) ||
      Object.values(item.attributes || {}).some((value) => String(value).toLowerCase().includes(needle)),
    );
  }, [items, search]);

  const sortedItems = useMemo(() => sortItems(filteredItems, itemSort), [filteredItems, itemSort]);
  const recentItems = useMemo(() => sortItems(items, itemSort).slice(0, 8), [items, itemSort]);
  const itemEmptyMessage = search.trim()
    ? 'No products match your search.'
    : 'No products yet. Add your first item to get started.';
  const alerts = useMemo(() => flattenAlerts(items), [items]);
  const lowStock = items.filter((item) => Number(item.stock_quantity) < 5).length;
  const expiryAlerts = items.filter((item) => ['warning', 'watch', 'critical'].includes(item.ai?.expiry_risk?.risk_level)).length;
  const healthy = Math.max(items.length - lowStock - expiryAlerts, 0);

  const handleSortChange = (key) => {
    setItemSort((current) => (
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: 'asc' }
    ));
  };

  const openAddItem = () => {
    setEditingSku(null);
    setForm({
      ...emptyItem,
      industry: industry || '',
      attributes: { ...emptyItem.attributes },
    });
    setItemModal(true);
  };

  const openAddUser = () => {
    setEditingUserId(null);
    setUserForm(emptyUser);
    setUserModal(true);
  };

  const goToIndustriesSection = () => {
    setUserModal(false);
    setSection('industries');
    setPendingScrollTarget('industries');
  };

  const openAddIndustry = () => {
    setEditingIndustryKey(null);
    setIndustryForm({ ...emptyIndustry, task_keys: [...DEFAULT_INDUSTRY_TASKS] });
    setSetupRecommendation(null);
    setIndustryModal(true);
  };

  const openIndustryDraft = () => {
    setEditingIndustryKey(null);
    setIndustryModal(true);
  };

  const editIndustry = (record) => {
    const profile = record.profile || {};
    const workflow = profile.workflow || {};
    const reorder = profile.reorder || {};
    setEditingIndustryKey(record.key);
    setIndustryForm({
      key: record.key,
      display_name: record.display_name,
      description: record.description || '',
      task_keys: [...(record.enabled_tasks || profile.enabled_tasks || [])],
      track_expiry: Boolean(profile.track_expiry),
      track_batch: Boolean(profile.track_batch),
      dynamic_attributes: attributesToText(profile.dynamic_attributes || {}),
      minimum_stock: workflow.minimum_stock ?? 10,
      expiry_warning_days: workflow.expiry_warning_days ?? 30,
      lead_time_days: reorder.lead_time_days ?? 7,
      safety_stock_multiplier: reorder.safety_stock_multiplier ?? 1.25,
      minimum_order_quantity: reorder.minimum_order_quantity ?? 5,
    });
    setSetupRecommendation(null);
    setIndustryModal(true);
  };

  const toggleIndustryTask = (taskKey) => {
    const selected = new Set(industryForm.task_keys);
    if (selected.has(taskKey)) selected.delete(taskKey);
    else selected.add(taskKey);
    setIndustryForm({ ...industryForm, task_keys: Array.from(selected) });
  };

  const applyRecommendedTasks = (taskKeys) => {
    if (!taskKeys?.length) return;
    const config = setupRecommendation?.recommended_config || {};
    const workflow = config.workflow || {};
    const reorder = config.reorder || {};
    setIndustryForm({
      ...industryForm,
      task_keys: [...taskKeys],
      track_expiry: config.track_expiry ?? industryForm.track_expiry,
      track_batch: config.track_batch ?? industryForm.track_batch,
      dynamic_attributes: config.dynamic_attributes ? attributesToText(config.dynamic_attributes) : industryForm.dynamic_attributes,
      minimum_stock: workflow.minimum_stock ?? industryForm.minimum_stock,
      expiry_warning_days: workflow.expiry_warning_days ?? industryForm.expiry_warning_days,
      lead_time_days: reorder.lead_time_days ?? industryForm.lead_time_days,
      safety_stock_multiplier: reorder.safety_stock_multiplier ?? industryForm.safety_stock_multiplier,
      minimum_order_quantity: reorder.minimum_order_quantity ?? industryForm.minimum_order_quantity,
    });
  };

  const editUser = (user) => {
    setEditingUserId(user.id);
    setUserForm({
      username: user.username,
      full_name: user.full_name,
      password: '',
      role: user.role,
      industries: [...(user.industries || [])],
      is_active: user.is_active,
    });
    setUserModal(true);
  };

  const editItem = (item) => {
    setEditingSku(item.sku);
    setForm({
      sku: item.sku,
      name: item.name,
      industry: item.industry,
      stock_quantity: item.stock_quantity,
      unit_cost: item.unit_cost,
      expiry_date: item.expiry_date || '',
      attributes: {
        category: item.attributes?.category || '',
        supplier: item.attributes?.supplier || '',
        location: item.attributes?.location || '',
        lead_time_days: item.attributes?.lead_time_days || '',
        batch_number: item.attributes?.batch_number || '',
        asset_tag: item.attributes?.asset_tag || '',
        warranty_expiry: item.attributes?.warranty_expiry || '',
        image_data: item.attributes?.image_data || '',
      },
    });
    setItemModal(true);
  };

  const saveItem = async () => {
    if (itemSubmitting) return;
    const stockQuantity = Number(form.stock_quantity);
    const unitCost = Number(form.unit_cost);
    if (!form.sku?.trim() || !form.name?.trim() || !form.industry?.trim()) {
      showToast('SKU, name, and industry are required.', 'error');
      return;
    }
    if (!Number.isInteger(stockQuantity) || stockQuantity < 0) {
      showToast('Stock must be a non-negative integer.', 'error');
      return;
    }
    if (!Number.isFinite(unitCost) || unitCost <= 0) {
      showToast('Unit cost must be a positive number.', 'error');
      return;
    }
    const payload = {
      sku: form.sku.trim().toUpperCase(),
      name: form.name.trim(),
      industry: form.industry.trim(),
      stock_quantity: stockQuantity,
      unit_cost: unitCost,
      expiry_date: form.expiry_date || null,
      attributes: Object.fromEntries(Object.entries(form.attributes).filter(([, value]) => value !== '')),
    };
    setItemSubmitting(true);
    try {
      if (editingSku) {
        await apiFetch(`/inventory/items/${editingSku}`, {
          method: 'PATCH',
          body: JSON.stringify({
            name: payload.name,
            stock_quantity: payload.stock_quantity,
            unit_cost: payload.unit_cost,
            expiry_date: payload.expiry_date,
            attributes: payload.attributes,
          }),
        });
        showToast('Item updated.');
      } else {
        await apiFetch('/inventory/items', { method: 'POST', body: JSON.stringify(payload) });
        showToast('Item added.');
      }
      setForm({ ...emptyItem, attributes: { ...emptyItem.attributes } });
      setItemModal(false);
      await loadData();
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      setItemSubmitting(false);
    }
  };

  const deleteItem = async (sku) => {
    if (!window.confirm(`Delete ${sku}?`)) return;
    try {
      await apiFetch(`/inventory/items/${sku}`, { method: 'DELETE' });
      showToast('Item deleted.');
      await loadData();
    } catch (error) {
      showToast(error.message, 'error');
    }
  };

  const saveTransaction = async () => {
    if (txSubmitting) return;
    const change = Number(txForm.change);
    if (!txForm.sku?.trim() || Number.isNaN(change) || change === 0) {
      showToast('SKU and non-zero change are required.', 'error');
      return;
    }
    setTxSubmitting(true);
    try {
      await apiFetch('/inventory/transactions', {
        method: 'POST',
        body: JSON.stringify({
          sku: txForm.sku.trim().toUpperCase(),
          change,
          reason: txForm.reason,
        }),
      });
      showToast('Transaction recorded.');
      setTxModal(false);
      setTxForm({ sku: '', change: '', reason: '' });
      await loadData();
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      setTxSubmitting(false);
    }
  };

  const runAi = async (kind, sku) => {
    if (!sku) {
      showToast('Enter a SKU first.', 'error');
      return;
    }
    try {
      const payload = await apiFetch(`/inventory/${sku}/ai`);
      setAiResults((current) => ({ ...current, [kind]: payload }));
    } catch (error) {
      showToast(error.message, 'error');
    }
  };

  const login = async () => {
    if (loginSubmitting) return;
    setLoginSubmitting(true);
    try {
      const payload = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify(loginForm),
      });
      setAuthToken(payload.access_token);
      setCurrentUser(payload.user);
      showToast('Logged in.');
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      setLoginSubmitting(false);
    }
  };

  const logout = () => {
    clearAuthToken();
    setCurrentUser(null);
    setItems([]);
    setTransactions([]);
    setUsers([]);
    setSection('dashboard');
  };

  const saveUser = async () => {
    if (userSubmitting) return;
    const industriesList = userForm.role === 'super_admin'
      ? []
      : (Array.isArray(userForm.industries) ? userForm.industries : []).map((value) => String(value).trim()).filter(Boolean);
    const payload = {
      username: userForm.username.trim().toLowerCase(),
      full_name: userForm.full_name.trim(),
      role: userForm.role,
      industries: industriesList,
      is_active: userForm.is_active,
    };
    if (userForm.password) payload.password = userForm.password;
    if (!payload.username || !payload.full_name || !payload.role) {
      showToast('Username, full name, and role are required.', 'error');
      return;
    }
    if (!editingUserId && !payload.password) {
      showToast('Password is required for new users.', 'error');
      return;
    }
    setUserSubmitting(true);
    try {
      if (editingUserId) {
        await apiFetch(`/users/${editingUserId}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
        showToast('User updated.');
      } else {
        await apiFetch('/users', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        showToast('User created.');
      }
      setUserForm(emptyUser);
      setUserModal(false);
      await loadUsers();
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      setUserSubmitting(false);
    }
  };

  const saveIndustry = async () => {
    if (industrySubmitting) return;
    if (!industryForm.display_name?.trim() || industryForm.task_keys.length === 0) {
      showToast('Industry name and at least one task are required.', 'error');
      return;
    }
    setIndustrySubmitting(true);
    const dynamicAttributes = parseAttributes(industryForm.dynamic_attributes);
    const configPayload = {
      fields: fieldsFromAttributes(dynamicAttributes),
      track_expiry: Boolean(industryForm.track_expiry),
      track_batch: Boolean(industryForm.track_batch),
      dynamic_attributes: dynamicAttributes,
      workflow: {
        minimum_stock: Number(industryForm.minimum_stock) || 0,
        expiry_warning_days: industryForm.track_expiry ? Number(industryForm.expiry_warning_days) || 30 : null,
        reorder_review_required: true,
      },
      reorder: {
        lead_time_days: Number(industryForm.lead_time_days) || 7,
        safety_stock_multiplier: Number(industryForm.safety_stock_multiplier) || 1.25,
        minimum_order_quantity: Number(industryForm.minimum_order_quantity) || 1,
      },
      expiry: {
        enabled: Boolean(industryForm.track_expiry),
        warning_days: Number(industryForm.expiry_warning_days) || 30,
        critical_days: 7,
      },
    };
    try {
      if (editingIndustryKey) {
        await apiFetch(`/industries/${editingIndustryKey}/tasks`, {
          method: 'PUT',
          body: JSON.stringify({ task_keys: industryForm.task_keys }),
        });
        await apiFetch(`/industries/${editingIndustryKey}/config`, {
          method: 'PATCH',
          body: JSON.stringify(configPayload),
        });
        showToast('Industry updated.');
      } else {
        await apiFetch('/industries', {
          method: 'POST',
          body: JSON.stringify({
            key: industryForm.key || undefined,
            display_name: industryForm.display_name,
            description: industryForm.description,
            task_keys: industryForm.task_keys,
            track_expiry: Boolean(industryForm.track_expiry),
            track_batch: Boolean(industryForm.track_batch),
            dynamic_attributes: dynamicAttributes,
            fields: configPayload.fields,
            workflow: configPayload.workflow,
            reorder: configPayload.reorder,
            expiry: configPayload.expiry,
          }),
        });
        showToast('Industry created.');
      }
      setIndustryForm({ ...emptyIndustry, task_keys: [...DEFAULT_INDUSTRY_TASKS] });
      setIndustryModal(false);
      await loadData();
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      setIndustrySubmitting(false);
    }
  };

  const askSetupAssistant = async () => {
    const message = chatInput.trim();
    if (!message) return;
    const userMessage = { role: 'user', content: message };
    setChatMessages((current) => [...current, userMessage]);
    setChatInput('');
    setChatLoading(true);
    try {
      const payload = await apiFetch('/ai/industry-setup-chat', {
        method: 'POST',
        body: JSON.stringify({
          industry: industryForm.key || industryForm.display_name,
          display_name: industryForm.display_name,
          selected_tasks: industryForm.task_keys,
          message,
          history: chatMessages.slice(-8),
        }),
      });
      if (payload.inferred_industry && payload.inferred_display_name && !industryForm.display_name) {
        setIndustryForm((current) => ({
          ...current,
          key: current.key || payload.inferred_industry,
          display_name: current.display_name || payload.inferred_display_name,
        }));
      }
      setSetupRecommendation(payload.recommendation_ready ? payload : null);
      const providerLine = payload.used_external_ai
        ? `\n\nProvider: ${payload.provider}`
        : payload.provider_error
          ? `\n\nProvider: ${payload.provider} failed. Check the API key/model in the backend terminal.`
          : payload.provider === 'local'
            ? ''
            : '\n\nProvider: local fallback';
      setChatMessages((current) => [...current, { role: 'assistant', content: `${payload.reply}${providerLine}` }]);
    } catch (error) {
      showToast(error.message, 'error');
      setChatMessages((current) => [...current, { role: 'assistant', content: `Setup assistant unavailable: ${error.message}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  const deleteUser = async (userId) => {
    if (!window.confirm('Delete this user?')) return;
    try {
      await apiFetch(`/users/${userId}`, { method: 'DELETE' });
      showToast('User deleted.');
      await loadUsers();
    } catch (error) {
      showToast(error.message, 'error');
    }
  };

  if (!authReady) {
    return <div className="login-screen"><div className="login-panel">Loading...</div></div>;
  }

  if (!currentUser) {
    return (
      <div className="login-screen">
        <div className="login-panel">
          <div className="login-brand">InvAI</div>
          <div className="login-title">Role-Based Access</div>
          <div className="form-grid one">
            <Input label="Username" value={loginForm.username} onChange={(value) => setLoginForm({ ...loginForm, username: value })} />
            <Input label="Password" type="password" value={loginForm.password} onChange={(value) => setLoginForm({ ...loginForm, password: value })} />
          </div>
          <button className="btn btn-primary login-btn" onClick={login} disabled={loginSubmitting}>{loginSubmitting ? 'Signing in...' : 'Log In'}</button>
          <div className="login-hint">Default Super Admin: superadmin / admin123</div>
        </div>
      </div>
    );
  }

  return (
    <div className={`layout ${sidebarCollapsed ? 'sidebar-collapsed' : 'sidebar-expanded'}`} style={{ '--sidebar-width': sidebarCollapsed ? '64px' : '230px' }}>
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-mark">InvAI</div>
          <div className="logo-sub">Inventory System</div>
        </div>
        <nav className="nav">
          {visibleNav.map((item, index) => (
            <React.Fragment key={item.id}>
              {(index === 0 || visibleNav[index - 1].group !== item.group) && <div className="nav-label">{item.group}</div>}
              <button
                className={`nav-item ${section === item.id ? 'active' : ''}`}
                data-show-add-item={String(Boolean(item.showAddItem))}
                title={sidebarCollapsed ? item.label : undefined}
                aria-label={item.label}
                onClick={() => setSection(item.id)}
              >
                <Icon type={item.icon} />
                <span className="nav-item-label">{item.label}</span>
                {item.id === 'alerts' && alerts.length > 0 && <span className="alert-badge">{alerts.length}</span>}
              </button>
            </React.Fragment>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-footer-info">
            <div className="api-status">
              <div className={`status-dot ${status}`} />
              <span>API {status}</span>
            </div>
            <div className="api-user">{currentUser.username} - {roleLabel(currentUser.role)}</div>
            <div className="api-url">{API.replace('http://', '')}</div>
          </div>
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed((current) => !current)}
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <Icon type={sidebarCollapsed ? 'chevron-right' : 'chevron-left'} />
          </button>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="topbar-title">{TITLES[section]}</div>
          <div className="topbar-right">
            <select className="industry-select" value={industry} onChange={(event) => setIndustry(event.target.value)}>
              <option value="">All Industries</option>
              {Object.keys(industries).map((key) => <option key={key} value={key}>{industryDisplayName(key, industries)}</option>)}
            </select>
            <button className="btn btn-ghost" onClick={() => loadData().catch((error) => showToast(error.message, 'error'))} disabled={dataLoading}>{dataLoading ? 'Refreshing...' : 'Refresh'}</button>
            <button
              className={`btn btn-primary topbar-add-item ${showAddItemButton ? 'visible' : 'hidden'}`}
              data-show-add-item={String(Boolean(activeNavItem?.showAddItem))}
              onClick={openAddItem}
              disabled={!showAddItemButton}
              aria-hidden={!showAddItemButton}
              tabIndex={showAddItemButton ? 0 : -1}
            >
              + Add Item
            </button>
            <button className="btn btn-ghost" onClick={logout}>Logout</button>
          </div>
        </div>

        <div className="content" ref={contentRef}>
          {dataLoading && (
            <div className="page-loader">
              <div className="spinner" />
              <div>Loading data...</div>
            </div>
          )}
          {section === 'dashboard' && (
            <section className="section active">
              <div className="stats-grid">
                <StatCard label="Total Items" value={items.length} sub="across selected industries" color="var(--accent)" />
                <StatCard label="Low Stock" value={lowStock} sub="below workflow threshold" color="var(--red)" />
                <StatCard label="Expiry Alerts" value={expiryAlerts} sub="watch, warning, or critical" color="var(--amber)" />
                <StatCard label="Healthy Items" value={healthy} sub="no immediate stock issue" color="var(--green)" />
              </div>
              <div className="section-header">
                <div className="section-title">Recent Items</div>
                <button className="btn btn-ghost btn-sm" onClick={() => setSection('items')}>View All</button>
              </div>
              <ItemsTable
                items={recentItems}
                compact
                canManage={false}
                onEdit={editItem}
                onDelete={deleteItem}
                emptyMessage="No products have been added yet."
              />
            </section>
          )}

          {section === 'items' && (
            <section className="section active">
              <div className="section-header">
                <div className="section-title">Inventory Items</div>
                <div className="flex items-center gap-8">
                  <input className="search-input" placeholder="Search products by name..." value={search} onChange={(event) => setSearch(event.target.value)} />
                  {canManage && <button className="btn btn-primary btn-sm" onClick={openAddItem}>+ Add Item</button>}
                </div>
              </div>
              <ItemsTable
                items={sortedItems}
                canManage={canManage}
                onEdit={editItem}
                onDelete={deleteItem}
                sortConfig={itemSort}
                onSortChange={handleSortChange}
                emptyMessage={itemEmptyMessage}
              />
            </section>
          )}

          {section === 'transactions' && canManage && (
            <section className="section active">
              <div className="section-header">
                <div className="section-title">Transaction History</div>
                <button className="btn btn-primary btn-sm" onClick={() => setTxModal(true)}>Record Transaction</button>
              </div>
              <TransactionsTable transactions={transactions} />
            </section>
          )}

          {section === 'admin' && isSuper && (
            <section className="section active">
              <div className="section-header">
                <div className="section-title">Users and Roles</div>
                <button className="btn btn-primary btn-sm" onClick={openAddUser}>+ Create User</button>
              </div>
              <UsersTable users={users} onEdit={editUser} onDelete={deleteUser} />
            </section>
          )}

          {section === 'industries' && isSuper && (
            <section className="section active" id="industries-section">
              <div className="industry-layout">
                <div>
                  <div className="section-header">
                    <div className="section-title">Industries and Modules</div>
                    <button className="btn btn-primary btn-sm" onClick={openAddIndustry}>+ Add Industry</button>
                  </div>
                  <IndustriesTable
                    records={industryRecords}
                    taskModules={taskModules}
                    onEdit={editIndustry}
                  />
                </div>
                <SetupAssistant
                  form={industryForm}
                  setForm={setIndustryForm}
                  taskModules={taskModules}
                  messages={chatMessages}
                  input={chatInput}
                  setInput={setChatInput}
                  loading={chatLoading}
                  recommendation={setupRecommendation}
                  onAsk={askSetupAssistant}
                  onApply={applyRecommendedTasks}
                  onOpenDraft={openIndustryDraft}
                />
              </div>
            </section>
          )}

          {section === 'alerts' && (
            <section className="section active">
              <div className="section-header"><div className="section-title">Active Alerts</div></div>
              <div className="alerts-grid">
                {alerts.length ? alerts.map((alert, index) => <AlertCard key={`${alert.sku}-${index}`} alert={alert} />) : <div className="table-empty ok">No active alerts.</div>}
              </div>
            </section>
          )}

          {section === 'ai' && (
            <section className="section active">
              <div className="section-header"><div className="section-title">AI Engine</div></div>
              <div className="ai-grid">
                <AiCard
                  kind="forecast"
                  icon="AI"
                  title="Demand Forecasting"
                  subtitle="LinearRegression - scikit-learn"
                  desc="Predict future demand from saved transaction history."
                  sku={aiSku}
                  setSku={setAiSku}
                  result={aiResults.forecast}
                  onRun={() => runAi('forecast', aiSku)}
                />
                <AiCard
                  kind="reorder"
                  icon="RO"
                  title="Reorder Recommendation"
                  subtitle="Forecast + profile policy"
                  desc="Get advisory reorder quantities without auto-ordering stock."
                  sku={aiSku}
                  setSku={setAiSku}
                  result={aiResults.reorder}
                  onRun={() => runAi('reorder', aiSku)}
                />
                <AiCard
                  kind="anomaly"
                  icon="AN"
                  title="Anomaly Detection"
                  subtitle="LinearRegression residual z-score"
                  desc="Detect unusual spikes or drops in sales transactions."
                  sku={aiSku}
                  setSku={setAiSku}
                  result={aiResults.anomaly}
                  onRun={() => runAi('anomaly', aiSku)}
                />
                <AiCard
                  kind="expiry"
                  icon="EX"
                  title="Expiry Risk Analysis"
                  subtitle="LinearRegression risk curve"
                  desc="Score expiry or warranty risk using profile rules."
                  sku={aiSku}
                  setSku={setAiSku}
                  result={aiResults.expiry}
                  onRun={() => runAi('expiry', aiSku)}
                />
              </div>
            </section>
          )}
        </div>
      </main>

        {itemModal && (
          <ItemModal
            form={form}
            setForm={setForm}
            editingSku={editingSku}
            industries={industries}
            onClose={() => setItemModal(false)}
            onSave={saveItem}
            submitting={itemSubmitting}
          />
        )}

        {txModal && (
          <TransactionModal
            form={txForm}
            setForm={setTxForm}
            onClose={() => setTxModal(false)}
            onSave={saveTransaction}
            submitting={txSubmitting}
          />
        )}

        {userModal && (
          <UserModal
            form={userForm}
            setForm={setUserForm}
            editingUserId={editingUserId}
            industryMap={industries}
            onClose={() => setUserModal(false)}
            onSave={saveUser}
            onAddNewIndustry={goToIndustriesSection}
            submitting={userSubmitting}
          />
        )}

        {industryModal && (
          <IndustryModal
            form={industryForm}
            setForm={setIndustryForm}
            editingIndustryKey={editingIndustryKey}
            taskModules={taskModules}
            onToggleTask={toggleIndustryTask}
            onClose={() => setIndustryModal(false)}
            onSave={saveIndustry}
            submitting={industrySubmitting}
          />
        )}

      {toast && <div className={`toast show ${toast.type}`}>{toast.message}</div>}
    </div>
  );
}

function StatCard({ label, value, sub, color }) {
  return (
    <div className="stat-card" style={{ '--accent-color': color }}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  );
}

function ItemsTable({ items, compact = false, canManage = false, onEdit, onDelete, sortConfig, onSortChange, emptyMessage = 'No products found.' }) {
  const canSort = Boolean(sortConfig && onSortChange && !compact);
  const sortLabel = (field, label) => {
    if (!canSort) return label;
    const active = sortConfig.key === field;
    const direction = active ? (sortConfig.direction === 'asc' ? '▲' : '▼') : '↕';
    return (
      <button type="button" className="sort-button" onClick={() => onSortChange(field)}>
        <span>{label}</span>
        <span className="sort-indicator">{direction}</span>
      </button>
    );
  };
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{sortLabel('sku', 'SKU')}</th>
            <th>{sortLabel('name', 'Name')}</th>
            <th>Industry</th>
            <th>{sortLabel('stock_quantity', 'Qty')}</th>
            {!compact && <><th>{sortLabel('unit_cost', 'Cost')}</th><th>Supplier</th><th>Expiry</th></>}
            <th>Status</th>{!compact && canManage && <th></th>}
          </tr>
        </thead>
        <tbody>
          {items.length ? items.map((item) => {
            const status = statusFor(item);
            const isLowStock = Number(item.stock_quantity) < 5;
            return (
              <tr key={item.sku} className={isLowStock ? 'row-warning' : ''}>
                <td><span className="sku-text">{item.sku}</span></td>
                <td>{item.name}</td>
                <td><span className={`badge ${industryBadge(item.industry)}`}>{displayIndustry(item.industry)}</span></td>
                <td><span className={`qty-badge ${quantityClass(item)}`}>{item.stock_quantity}</span></td>
                {!compact && <>
                  <td className="text-muted">PHP {Number(item.unit_cost).toLocaleString()}</td>
                  <td className="text-muted">{item.attributes?.supplier || '-'}</td>
                  <td className="text-muted">{formatDate(item.expiry_date || item.attributes?.warranty_expiry)}</td>
                </>}
                <td><span className={`badge ${status.className}`}>{status.label}</span></td>
                {!compact && canManage && (
                  <td>
                    <div className="flex gap-8">
                      <button className="btn btn-ghost btn-sm" onClick={() => onEdit(item)}>Edit</button>
                      <button className="btn btn-danger btn-sm" onClick={() => onDelete(item.sku)}>Del</button>
                    </div>
                  </td>
                )}
              </tr>
            );
          }) : <tr><td colSpan={compact ? 5 : canManage ? 9 : 8} className="table-empty">{emptyMessage}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function UsersTable({ users, onEdit, onDelete }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Industries</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {users.length ? users.map((user) => (
            <tr key={user.id}>
              <td><span className="sku-text">{user.username}</span></td>
              <td>{user.full_name}</td>
              <td><span className="badge badge-blue">{roleLabel(user.role)}</span></td>
              <td className="text-muted">{user.role === 'super_admin' ? 'All Industries' : (user.industries || []).join(', ')}</td>
              <td><span className={`badge ${user.is_active ? 'badge-green' : 'badge-red'}`}>{user.is_active ? 'Active' : 'Inactive'}</span></td>
              <td>
                <div className="flex gap-8">
                  <button className="btn btn-ghost btn-sm" onClick={() => onEdit(user)}>Edit</button>
                  <button className="btn btn-danger btn-sm" onClick={() => onDelete(user.id)}>Del</button>
                </div>
              </td>
            </tr>
          )) : <tr><td colSpan="6" className="table-empty">No users found.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function IndustriesTable({ records, taskModules, onEdit }) {
  const taskNames = Object.fromEntries(taskModules.map((task) => [task.key, task.display_name]));
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Industry</th><th>Modules</th><th>Tracking</th><th>Type</th><th></th></tr></thead>
        <tbody>
          {records.length ? records.map((record) => {
            const profile = record.profile || {};
            const enabled = record.enabled_tasks || profile.enabled_tasks || [];
            const moduleText = enabled.slice(0, 4).map((key) => taskNames[key] || titleCase(key)).join(', ');
            const extraCount = Math.max(enabled.length - 4, 0);
            return (
              <tr key={record.key}>
                <td>
                  <span className="sku-text">{record.display_name}</span>
                  <div className="table-sub">{record.key}</div>
                </td>
                <td className="text-muted">
                  {moduleText || '-'}{extraCount ? ` +${extraCount} more` : ''}
                </td>
                <td>
                  <div className="flex gap-8">
                    <span className={`badge ${profile.track_expiry ? 'badge-amber' : 'badge-blue'}`}>{profile.track_expiry ? 'Expiry' : 'No Expiry'}</span>
                    <span className={`badge ${profile.track_batch ? 'badge-purple' : 'badge-green'}`}>{profile.track_batch ? 'Batch' : 'Standard'}</span>
                  </div>
                </td>
                <td><span className={`badge ${record.is_system ? 'badge-blue' : 'badge-green'}`}>{record.is_system ? 'System' : 'Custom'}</span></td>
                <td><button className="btn btn-ghost btn-sm" onClick={() => onEdit(record)}>Edit Modules</button></td>
              </tr>
            );
          }) : <tr><td colSpan="5" className="table-empty">No industries found.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function SetupAssistant({
  form,
  setForm,
  taskModules,
  messages,
  input,
  setInput,
  loading,
  recommendation,
  onAsk,
  onApply,
  onOpenDraft,
}) {
  const recommended = recommendation?.recommended_task_keys || [];
  const missing = recommendation?.add_task_keys || [];
  return (
    <div className="setup-card">
      <div className="section-header compact">
        <div className="section-title">Setup Assistant</div>
        <button className="btn btn-ghost btn-sm" onClick={onOpenDraft}>Open Form</button>
      </div>
      <div className="form-grid one">
        <Input label="Draft Industry" value={form.display_name} onChange={(value) => setForm({ ...form, display_name: value })} placeholder="Food Service, Logistics, Pharmacy" />
        <Input label="Key" value={form.key} onChange={(value) => setForm({ ...form, key: value.toLowerCase().replaceAll(' ', '_') })} placeholder="Optional" />
      </div>
      <div className="assistant-task-row">
        {form.task_keys.map((taskKey) => (
          <span className="task-pill" key={taskKey}>{taskModules.find((task) => task.key === taskKey)?.display_name || titleCase(taskKey)}</span>
        ))}
      </div>
      <div className="chat-window">
        {messages.map((message, index) => (
          <div className={`chat-bubble ${message.role}`} key={`${message.role}-${index}`}>{message.content}</div>
        ))}
        {loading && <div className="chat-bubble assistant">Thinking through the setup...</div>}
      </div>
      {recommendation && (
        <div className="recommendation-box">
          <div className="recommendation-title">Recommended Modules</div>
          <div className="assistant-task-row">
            {recommended.map((taskKey) => <span className="task-pill strong" key={taskKey}>{titleCase(taskKey)}</span>)}
          </div>
          <div className="recommendation-note">Missing from draft: {missing.length ? missing.map(titleCase).join(', ') : 'none'}</div>
          <button className="btn btn-primary btn-sm" onClick={() => onApply(recommended)}>Apply Setup</button>
        </div>
      )}
      <div className="chat-input-row">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') onAsk();
          }}
          placeholder="Ask for module recommendations..."
        />
        <button className="btn btn-primary btn-sm" onClick={onAsk} disabled={loading}>Ask</button>
      </div>
    </div>
  );
}

function TransactionsTable({ transactions }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>ID</th><th>SKU</th><th>Change</th><th>Reason</th><th>Timestamp</th></tr></thead>
        <tbody>
          {transactions.length ? transactions.map((tx) => {
            const change = tx.transaction_type === 'sale' ? -tx.quantity : tx.quantity;
            return (
              <tr key={tx.id}>
                <td className="text-muted">#{tx.id}</td>
                <td><span className="sku-text">{tx.sku}</span></td>
                <td><span className={`badge ${change < 0 ? 'badge-red' : 'badge-green'}`}>{change > 0 ? '+' : ''}{change}</span></td>
                <td className="text-muted">{tx.notes || tx.transaction_type}</td>
                <td className="text-muted">{formatDate(tx.transaction_date)}</td>
              </tr>
            );
          }) : <tr><td colSpan="5" className="table-empty">No transactions yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function AlertCard({ alert }) {
  const badge = alert.severity === 'critical' ? 'badge-red' : alert.severity === 'warning' ? 'badge-amber' : 'badge-blue';
  return (
    <div className={`alert-card ${alert.severity}`}>
      <div className="alert-icon">{alert.severity === 'critical' ? '!' : alert.severity === 'warning' ? '?' : 'i'}</div>
      <div className="alert-body">
        <div className="alert-title">{alert.name} <span className={`badge ${badge}`}>{alert.title}</span></div>
        <div className="alert-sub">SKU: {alert.sku} - Industry: {displayIndustry(alert.industry)} - {alert.detail}</div>
      </div>
    </div>
  );
}

function AiCard({ kind, icon, title, subtitle, desc, sku, setSku, result, onRun }) {
  const data = result?.ai;
  return (
    <div className="ai-card">
      <div className="ai-card-header">
        <div className={`ai-icon ai-${kind}`}>{icon}</div>
        <div>
          <div className="ai-card-title">{title}</div>
          <div className="ai-card-subtitle">{subtitle}</div>
        </div>
      </div>
      <div className="ai-card-desc">{desc}</div>
      <div className="form-group">
        <label>SKU</label>
        <input value={sku} onChange={(event) => setSku(event.target.value.toUpperCase())} placeholder="e.g. RTL-COF-001" />
      </div>
      <button className="btn btn-primary btn-sm" onClick={onRun}>Run Analysis</button>
      {data && <AiResult kind={kind} payload={data} />}
    </div>
  );
}

function AiResult({ kind, payload }) {
  let rows = [];
  let recommendation = '';
  if (kind === 'forecast') {
    rows = [
      ['Model', payload.forecast.method],
      ['Total Forecast', payload.forecast.total_forecast],
      ['Trend / Day', payload.forecast.trend_per_day],
    ];
    recommendation = payload.forecast.confidence_note;
  } else if (kind === 'reorder') {
    rows = [
      ['Decision', payload.reorder.decision],
      ['Current Stock', payload.reorder.current_stock],
      ['Suggested Order', payload.reorder.suggested_order_quantity],
      ['Target Stock', payload.reorder.target_stock],
    ];
    recommendation = payload.reorder.advisory_note;
  } else if (kind === 'anomaly') {
    rows = [
      ['Method', payload.anomaly_detection.method],
      ['Anomalies', payload.anomaly_detection.anomalies.length],
      ['Summary', payload.anomaly_detection.summary],
    ];
  } else {
    rows = [
      ['Risk Level', payload.expiry_risk.risk_level],
      ['Risk Score', payload.expiry_risk.risk_score],
      ['Days to Expiry', payload.expiry_risk.days_to_expiry ?? 'N/A'],
    ];
    recommendation = payload.expiry_risk.advisory_note;
  }
  return (
    <div className="ai-result visible">
      {rows.map(([key, value]) => (
        <div className="result-row" key={key}><span className="result-key">{key}</span><span className="result-val">{value}</span></div>
      ))}
      {recommendation && <div className="result-rec">{recommendation}</div>}
    </div>
  );
}

function ItemModal({ form, setForm, editingSku, industries, onClose, onSave, submitting = false }) {
  const setAttr = (key, value) => setForm({ ...form, attributes: { ...form.attributes, [key]: value } });
  const onImageChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setAttr('image_data', String(reader.result || ''));
    reader.readAsDataURL(file);
  };
  return (
    <div className="modal-overlay open" onMouseDown={(event) => event.target.classList.contains('modal-overlay') && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <div className="modal-title">{editingSku ? 'Edit Item' : 'Add Item'}</div>
          <button className="modal-close" onClick={onClose}>x</button>
        </div>
        <div className="modal-body">
          <div className="form-grid">
            <Input label="SKU *" value={form.sku} disabled={Boolean(editingSku)} onChange={(value) => setForm({ ...form, sku: value.toUpperCase() })} />
            <Input label="Name *" value={form.name} onChange={(value) => setForm({ ...form, name: value })} />
            <div className="form-group">
              <label>Industry *</label>
              <select value={form.industry} onChange={(event) => setForm({ ...form, industry: event.target.value })}>
                <option value="">Select...</option>
                {Object.keys(industries).map((key) => <option key={key} value={key}>{displayIndustry(key)}</option>)}
              </select>
            </div>
            <Input label="Quantity *" type="number" value={form.stock_quantity} onChange={(value) => setForm({ ...form, stock_quantity: value })} />
            <Input label="Unit Cost" type="number" value={form.unit_cost} onChange={(value) => setForm({ ...form, unit_cost: value })} />
            <Input label="Category" value={form.attributes.category} onChange={(value) => setAttr('category', value)} />
            <Input label="Supplier" value={form.attributes.supplier} onChange={(value) => setAttr('supplier', value)} />
            <Input label="Location" value={form.attributes.location} onChange={(value) => setAttr('location', value)} />
            <Input label="Lead Time (days)" type="number" value={form.attributes.lead_time_days} onChange={(value) => setAttr('lead_time_days', value)} />
            <Input label="Batch Number" value={form.attributes.batch_number} onChange={(value) => setAttr('batch_number', value)} />
            <Input label="Asset Tag" value={form.attributes.asset_tag} onChange={(value) => setAttr('asset_tag', value)} />
            <Input label="Expiry Date" type="date" value={form.expiry_date} onChange={(value) => setForm({ ...form, expiry_date: value })} />
            <Input label="Warranty Expiry" type="date" value={form.attributes.warranty_expiry} onChange={(value) => setAttr('warranty_expiry', value)} />
            <div className="form-group form-span">
              <label>Item Image</label>
              <input type="file" accept="image/*" onChange={onImageChange} />
              {form.attributes.image_data && (
                <div className="image-preview">
                  <img src={form.attributes.image_data} alt="Selected item preview" />
                </div>
              )}
            </div>
          </div>
          <div className="form-actions">
            <button className="btn btn-ghost" onClick={onClose} disabled={submitting}>Cancel</button>
            <button className="btn btn-primary" onClick={onSave} disabled={submitting}>{submitting ? 'Saving...' : (editingSku ? 'Update Item' : 'Save Item')}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function TransactionModal({ form, setForm, onClose, onSave, submitting = false }) {
  return (
    <div className="modal-overlay open" onMouseDown={(event) => event.target.classList.contains('modal-overlay') && onClose()}>
      <div className="modal modal-sm">
        <div className="modal-header">
          <div className="modal-title">Record Transaction</div>
          <button className="modal-close" onClick={onClose}>x</button>
        </div>
        <div className="modal-body">
          <div className="form-grid one">
            <Input label="SKU *" value={form.sku} onChange={(value) => setForm({ ...form, sku: value.toUpperCase() })} />
            <Input label="Change *" type="number" value={form.change} onChange={(value) => setForm({ ...form, change: value })} placeholder="Positive = restock, negative = sale" />
            <Input label="Reason" value={form.reason} onChange={(value) => setForm({ ...form, reason: value })} />
          </div>
          <div className="form-actions">
            <button className="btn btn-ghost" onClick={onClose} disabled={submitting}>Cancel</button>
            <button className="btn btn-primary" onClick={onSave} disabled={submitting}>{submitting ? 'Saving...' : 'Record'}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function UserModal({
  form,
  setForm,
  editingUserId,
  industryMap,
  onAddNewIndustry,
  onClose,
  onSave,
  submitting = false,
}) {
  const selectedIndustries = Array.isArray(form.industries) ? form.industries : [];
  return (
    <div className="modal-overlay open" onMouseDown={(event) => event.target.classList.contains('modal-overlay') && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <div className="modal-title">{editingUserId ? 'Edit User' : 'Create User'}</div>
          <button className="modal-close" onClick={onClose}>x</button>
        </div>
        <div className="modal-body">
          <div className="form-grid">
            <Input label="Username *" value={form.username} onChange={(value) => setForm({ ...form, username: value.toLowerCase() })} />
            <Input label="Full Name *" value={form.full_name} onChange={(value) => setForm({ ...form, full_name: value })} />
            <Input label={editingUserId ? 'New Password' : 'Password *'} type="password" value={form.password} onChange={(value) => setForm({ ...form, password: value })} />
            <div className="form-group">
              <label>Role *</label>
              <select
                value={form.role}
                onChange={(event) => setForm({
                  ...form,
                  role: event.target.value,
                  industries: event.target.value === 'super_admin' ? [] : selectedIndustries,
                })}
              >
                <option value="user">User</option>
                <option value="industry_admin">Industry Admin</option>
                <option value="super_admin">Super Admin</option>
              </select>
            </div>
            <div className="form-group form-span">
              <label>Industries</label>
              <IndustryDropdown
                disabled={form.role === 'super_admin'}
                selected={selectedIndustries}
                industryMap={industryMap}
                onChange={(nextIndustries) => setForm({ ...form, industries: nextIndustries })}
                onAddNewIndustry={onAddNewIndustry}
              />
              {form.role === 'super_admin' && <div className="field-hint">Super Admins automatically access all industries.</div>}
            </div>
            <div className="form-group">
              <label>Status</label>
              <select value={form.is_active ? 'active' : 'inactive'} onChange={(event) => setForm({ ...form, is_active: event.target.value === 'active' })}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>
          <div className="form-actions">
            <button className="btn btn-ghost" onClick={onClose} disabled={submitting}>Cancel</button>
            <button className="btn btn-primary" onClick={onSave} disabled={submitting}>{submitting ? 'Saving...' : (editingUserId ? 'Update User' : 'Create User')}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function IndustryDropdown({ selected, industryMap, onChange, onAddNewIndustry, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef(null);

  const options = useMemo(() => {
    const entries = Object.entries(industryMap || {}).map(([key, profile]) => ({
      key,
      displayName: profile?.display_name || displayIndustry(key),
      description: profile?.description || '',
    }));
    return entries.sort((left, right) => compareText(left.displayName, right.displayName));
  }, [industryMap]);

  const filteredOptions = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((option) =>
      option.key.toLowerCase().includes(needle) ||
      option.displayName.toLowerCase().includes(needle) ||
      option.description.toLowerCase().includes(needle),
    );
  }, [options, query]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (disabled) {
      setOpen(false);
      setQuery('');
    }
  }, [disabled]);

  const toggleIndustry = (key) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(Array.from(next));
  };

  const selectedNames = selected
    .map((key) => ({ key, label: industryDisplayName(key, industryMap) }))
    .sort((left, right) => compareText(left.label, right.label));

  return (
    <div className="industry-dropdown" ref={rootRef}>
      <button
        type="button"
        className={`industry-dropdown-trigger ${disabled ? 'disabled' : ''}`}
        onClick={() => !disabled && setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={disabled}
      >
        <div className="industry-dropdown-selected">
          {selectedNames.length ? selectedNames.map((item) => (
            <span className="industry-chip" key={item.key}>{item.label}</span>
          )) : <span className="industry-placeholder">Select one or more industries</span>}
        </div>
        <Icon type={open ? 'chevron-up' : 'chevron-down'} />
      </button>

      <div className={`industry-dropdown-panel ${open ? 'open' : ''}`}>
        <div className="industry-dropdown-search-wrap">
          <input
            className="industry-dropdown-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search industries..."
          />
        </div>

        <div className="industry-dropdown-list" role="listbox" aria-multiselectable="true">
          {filteredOptions.length ? filteredOptions.map((option) => {
            const isSelected = selected.includes(option.key);
            return (
              <button
                type="button"
                key={option.key}
                className={`industry-option ${isSelected ? 'selected' : ''}`}
                onClick={() => toggleIndustry(option.key)}
              >
                <div className="industry-option-main">
                  <span className="industry-option-title">{option.displayName}</span>
                  <span className="industry-option-key">{option.key}</span>
                </div>
                <span className="industry-option-check">{isSelected ? <Icon type="check" /> : null}</span>
              </button>
            );
          }) : <div className="industry-empty">No industries match your search.</div>}
        </div>

        <button
          type="button"
          className="industry-add-new"
          onClick={() => {
            setOpen(false);
            onAddNewIndustry();
          }}
        >
          <Icon type="plus" />
          <span>Add New Industry</span>
        </button>
      </div>
    </div>
  );
}

function IndustryModal({ form, setForm, editingIndustryKey, taskModules, onToggleTask, onClose, onSave, submitting = false }) {
  return (
    <div className="modal-overlay open" onMouseDown={(event) => event.target.classList.contains('modal-overlay') && onClose()}>
      <div className="modal modal-wide">
        <div className="modal-header">
          <div className="modal-title">{editingIndustryKey ? 'Configure Industry' : 'Add Industry'}</div>
          <button className="modal-close" onClick={onClose}>x</button>
        </div>
        <div className="modal-body">
          <div className="form-grid">
            <Input label="Display Name *" value={form.display_name} onChange={(value) => setForm({ ...form, display_name: value })} />
            <Input label="Key" value={form.key} disabled={Boolean(editingIndustryKey)} onChange={(value) => setForm({ ...form, key: value.toLowerCase().replaceAll(' ', '_') })} placeholder="auto-created from name" />
            <div className="form-group form-span">
              <label>Description</label>
              <textarea rows="2" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
            </div>
            <div className="form-group">
              <label>Expiry Tracking</label>
              <select value={form.track_expiry ? 'yes' : 'no'} onChange={(event) => setForm({ ...form, track_expiry: event.target.value === 'yes' })}>
                <option value="yes">Enabled</option>
                <option value="no">Disabled</option>
              </select>
            </div>
            <div className="form-group">
              <label>Batch Tracking</label>
              <select value={form.track_batch ? 'yes' : 'no'} onChange={(event) => setForm({ ...form, track_batch: event.target.value === 'yes' })}>
                <option value="yes">Enabled</option>
                <option value="no">Disabled</option>
              </select>
            </div>
            <Input label="Minimum Stock" type="number" value={form.minimum_stock} onChange={(value) => setForm({ ...form, minimum_stock: value })} />
            <Input label="Expiry Warning Days" type="number" value={form.expiry_warning_days} disabled={!form.track_expiry} onChange={(value) => setForm({ ...form, expiry_warning_days: value })} />
            <Input label="Lead Time Days" type="number" value={form.lead_time_days} onChange={(value) => setForm({ ...form, lead_time_days: value })} />
            <Input label="Safety Multiplier" type="number" value={form.safety_stock_multiplier} onChange={(value) => setForm({ ...form, safety_stock_multiplier: value })} />
            <Input label="Minimum Order Qty" type="number" value={form.minimum_order_quantity} onChange={(value) => setForm({ ...form, minimum_order_quantity: value })} />
            <div className="form-group form-span">
              <label>Dynamic Attributes</label>
              <textarea rows="4" value={form.dynamic_attributes} onChange={(event) => setForm({ ...form, dynamic_attributes: event.target.value })} />
            </div>
          </div>
          <div className="task-checklist-wrap">
            <div className="section-title small">Task Modules</div>
            <TaskChecklist taskModules={taskModules} selected={form.task_keys} onToggle={onToggleTask} />
          </div>
          <div className="form-actions">
            <button className="btn btn-ghost" onClick={onClose} disabled={submitting}>Cancel</button>
            <button className="btn btn-primary" onClick={onSave} disabled={submitting}>{submitting ? 'Saving...' : (editingIndustryKey ? 'Update Industry' : 'Create Industry')}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function TaskChecklist({ taskModules, selected, onToggle }) {
  const groups = taskModules.reduce((current, task) => {
    const category = task.category || 'General';
    current[category] = current[category] || [];
    current[category].push(task);
    return current;
  }, {});
  return (
    <div className="task-groups">
      {Object.entries(groups).map(([category, tasks]) => (
        <div className="task-group" key={category}>
          <div className="task-group-title">{category}</div>
          {tasks.map((task) => (
            <label className="task-checkbox" key={task.key}>
              <input type="checkbox" checked={selected.includes(task.key)} onChange={() => onToggle(task.key)} />
              <span>
                <strong>{task.display_name}</strong>
                <small>{task.description}</small>
              </span>
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

function Input({ label, value, onChange, type = 'text', disabled = false, placeholder = '' }) {
  return (
    <div className="form-group">
      <label>{label}</label>
      <input type={type} value={value ?? ''} disabled={disabled} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

export default App;
