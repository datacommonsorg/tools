import { describe, expect, it } from 'vitest';
import { normalizePlaceType } from './normalize_place_type';

describe('normalize_place_type', () => {
  describe('normalizePlaceType', () => {
    it('maps country aliases and plurals', () => {
      expect(normalizePlaceType('country')).toBe('Country');
      expect(normalizePlaceType('countries')).toBe('Country');
      expect(normalizePlaceType('nation')).toBe('Country');
      expect(normalizePlaceType('nations')).toBe('Country');
    });

    it('maps state and province aliases', () => {
      expect(normalizePlaceType('state')).toBe('State');
      expect(normalizePlaceType('states')).toBe('State');
      expect(normalizePlaceType('province')).toBe('State');
      expect(normalizePlaceType('provinces')).toBe('State');
    });

    it('maps county and department aliases', () => {
      expect(normalizePlaceType('county')).toBe('County');
      expect(normalizePlaceType('counties')).toBe('County');
      expect(normalizePlaceType('parish')).toBe('County');
      expect(normalizePlaceType('parishes')).toBe('County');
      expect(normalizePlaceType('department')).toBe('Department');
      expect(normalizePlaceType('departments')).toBe('Department');
    });

    it('maps city, town, village, and borough aliases', () => {
      expect(normalizePlaceType('city')).toBe('City');
      expect(normalizePlaceType('cities')).toBe('City');
      expect(normalizePlaceType('town')).toBe('Town');
      expect(normalizePlaceType('towns')).toBe('Town');
      expect(normalizePlaceType('village')).toBe('Village');
      expect(normalizePlaceType('villages')).toBe('Village');
      expect(normalizePlaceType('borough')).toBe('Borough');
      expect(normalizePlaceType('boroughs')).toBe('Borough');
      expect(normalizePlaceType('municipality')).toBe('City');
    });

    it('maps Eurostat NUTS variations', () => {
      expect(normalizePlaceType('nuts1')).toBe('EurostatNUTS1');
      expect(normalizePlaceType('nuts2')).toBe('EurostatNUTS2');
      expect(normalizePlaceType('nuts3')).toBe('EurostatNUTS3');
      expect(normalizePlaceType('eurostatnuts2')).toBe('EurostatNUTS2');
      expect(normalizePlaceType('eurostat_nuts_2')).toBe('EurostatNUTS2');
    });

    it('maps Census and administrative variations', () => {
      expect(normalizePlaceType('census_tract')).toBe('CensusTract');
      expect(normalizePlaceType('tract')).toBe('CensusTract');
      expect(normalizePlaceType('zip_code')).toBe(
        'CensusZipCodeTabulationArea',
      );
      expect(normalizePlaceType('zipcode')).toBe('CensusZipCodeTabulationArea');
      expect(normalizePlaceType('zip')).toBe('CensusZipCodeTabulationArea');
      expect(normalizePlaceType('administrative_area_1')).toBe(
        'AdministrativeArea1',
      );
      expect(normalizePlaceType('adminarea1')).toBe('AdministrativeArea1');
      expect(normalizePlaceType('administrative_area_2')).toBe(
        'AdministrativeArea2',
      );
      expect(normalizePlaceType('district')).toBe('AdministrativeArea2');
      expect(normalizePlaceType('districts')).toBe('AdministrativeArea2');
    });

    it('falls back to PascalCase for unknown types', () => {
      expect(normalizePlaceType('custom_region')).toBe('CustomRegion');
      expect(normalizePlaceType('special-zone')).toBe('SpecialZone');
      expect(normalizePlaceType('canton')).toBe('Canton');
    });

    it('defaults to Country when undefined, null, or empty string', () => {
      expect(normalizePlaceType(undefined)).toBe('Country');
      expect(normalizePlaceType('')).toBe('Country');
      expect(normalizePlaceType('   ')).toBe('Country');
    });
  });
});
