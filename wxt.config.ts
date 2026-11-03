import { defineConfig } from 'wxt';

export default defineConfig({
  manifestVersion: 3,
  manifest: {
    name: 'GYST',
    description: 'Get Your Shit Together: block distracting sites until you really mean it.',
    permissions: ['storage', 'webNavigation', 'tabs'],
    host_permissions: ['<all_urls>'],
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
