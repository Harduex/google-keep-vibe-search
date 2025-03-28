import { memo } from 'react';
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

export const TabNavigation = memo(({ activeTab, onChange }: TabNavigationProps) => {
  return (
    <div className="tab-navigation">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
          onClick={() => onChange(tab.id)}
          aria-label={tab.label}
          title={tab.label}
        >
          <span className="material-icons">{tab.icon}</span>
          <span>{tab.label}</span>
        </button>
      ))}
    </div>
  );
});

TabNavigation.displayName = 'TabNavigation';
