// Relay currently includes legacy authProviders without the SDK's oauth2 object.
export function normalizeAuthMethods(data) {
  if (!data || typeof data !== 'object') return data;
  const providers = data.oauth2?.providers ?? data.authProviders ?? [];
  return {
    ...data,
    oauth2: {
      enabled: data.oauth2?.enabled ?? providers.length > 0,
      providers: providers.map(provider => ({
        ...provider,
        authURL: provider.authURL || provider.authUrl,
      })),
    },
  };
}
