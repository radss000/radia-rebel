import { methodGroup, trackPosition } from './SonicUniverse';

describe('SonicUniverse data interpretation', () => {
  test('accepts complete finite 3D coordinates', () => {
    expect(trackPosition({ position: { x: '-12.5', y: 0, z: 42 } })).toEqual([-12.5, 0, 42]);
  });

  test('rejects partial or invalid coordinates', () => {
    expect(trackPosition({ position: { x: 0, y: null, z: 1 } })).toBeNull();
    expect(trackPosition({ position: { x: 0, y: 'invalid', z: 1 } })).toBeNull();
    expect(trackPosition({})).toBeNull();
  });

  test.each([
    ['clap_umap_full', 'full'],
    ['clap_knn_approx', 'approx'],
    ['features_fallback', 'fallback'],
    ['legacy', 'other']
  ])('maps %s provenance to %s', (positionMethod, expected) => {
    expect(methodGroup({ positionMethod })).toBe(expected);
  });
});
