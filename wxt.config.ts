import { defineConfig } from 'wxt';

export default defineConfig({
  manifestVersion: 3,
  manifest: {
    name: 'GYST',
    description: 'Get Your Shit Together: block distracting sites until you really mean it.',
    permissions: ['storage', 'webNavigation', 'tabs'],
    host_permissions: ['<all_urls>'],
    action: {
      default_icon: { 16: 'icon/16.png', 32: 'icon/32.png', 48: 'icon/48.png' },
    },
    browser_specific_settings: {
      gecko: {
        id: 'gyst@corixien.github.io',
        strict_min_version: '128.0',
        data_collection_permissions: {
          required: ['none'],
        },
      },
    },
  },
});
