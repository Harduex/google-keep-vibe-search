import { memo, useCallback } from 'react';
import './styles.css';

export type TabId = 'search' | 'clusters' | 'all-notes';

interface TabItem {
  id: TabId;
  label: string;
  icon: string;
}

interface TabNavigationProps {
  activeTab: TabId;
  onChange: (tab: TabId) => void;
}

const tabs: TabItem[] = [
  {
    id: 'search',
    label: 'Search',
    icon: 'search',
  },
  {
    id: 'all-notes',
    label: 'All Notes',
    icon: 'notes',
  },
  {
    id: 'clusters',
    label: 'Clusters',
    icon: 'bubble_chart',
  },
];

interface TabButtonProps {
  tab: TabItem;
  isActive: boolean;
  onTabChange: (tabId: TabId) => void;
}

const TabButton = memo(({ tab, isActive, onTabChange }: TabButtonProps) => {
  const handleClick = useCallback(() => {
    onTabChange(tab.id);
  }, [tab.id, onTabChange]);

  return (
    <button
      key={tab.id}
      className={`tab-button ${isActive ? 'active' : ''}`}
      onClick={handleClick}
      aria-label={tab.label}
      title={tab.label}
    >
      <span className="material-icons">{tab.icon}</span>
      <span>{tab.label}</span>
    </button>
  );
});

export const TabNavigation = memo(({ activeTab, onChange }: TabNavigationProps) => {
  return (
    <div className="tab-navigation">
      {tabs.map((tab) => (
        <TabButton key={tab.id} tab={tab} isActive={activeTab === tab.id} onTabChange={onChange} />
      ))}
    </div>
  );
});
