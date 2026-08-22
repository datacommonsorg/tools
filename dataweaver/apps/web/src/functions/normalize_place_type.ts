/**
 * Canonical mapping from common aliases, plurals, and variations
 * to official Data Commons schema Place types (PascalCase).
 * Sourced from Data Commons constants and place hierarchies.
 */
const PLACE_TYPE_MAP: Record<string, string> = {
  // Global & Continents
  continent: 'Continent',
  continents: 'Continent',
  georegion: 'GeoRegion',
  ungeoregion: 'UNGeoRegion',
  continentalunion: 'ContinentalUnion',
  oceanicbasin: 'OceanicBasin',

  // Countries
  country: 'Country',
  countries: 'Country',
  nation: 'Country',
  nations: 'Country',

  // States, Provinces & AdminArea1
  state: 'State',
  states: 'State',
  statecomponent: 'StateComponent',
  province: 'State',
  provinces: 'State',
  administrativearea: 'AdministrativeArea',
  administrativearea1: 'AdministrativeArea1',
  administrative_area_1: 'AdministrativeArea1',
  'administrative area 1': 'AdministrativeArea1',
  adminarea1: 'AdministrativeArea1',
  admin_area_1: 'AdministrativeArea1',
  prefecture: 'AdministrativeArea1',
  prefectures: 'AdministrativeArea1',

  // Counties, Departments & AdminArea2
  county: 'County',
  counties: 'County',
  parish: 'County',
  parishes: 'County',
  department: 'Department',
  departments: 'Department',
  district: 'AdministrativeArea2',
  districts: 'AdministrativeArea2',
  administrativearea2: 'AdministrativeArea2',
  administrative_area_2: 'AdministrativeArea2',
  'administrative area 2': 'AdministrativeArea2',
  adminarea2: 'AdministrativeArea2',
  admin_area_2: 'AdministrativeArea2',
  censuscountydivision: 'CensusCountyDivision',
  udisedistrict: 'UDISEDistrict',

  // Sub-County, AdminArea3-5
  administrativearea3: 'AdministrativeArea3',
  administrative_area_3: 'AdministrativeArea3',
  'administrative area 3': 'AdministrativeArea3',
  administrativearea4: 'AdministrativeArea4',
  administrativearea5: 'AdministrativeArea5',
  udiseblock: 'UDISEBlock',

  // Cities, Towns & Municipalities
  city: 'City',
  cities: 'City',
  town: 'Town',
  towns: 'Town',
  village: 'Village',
  villages: 'Village',
  borough: 'Borough',
  boroughs: 'Borough',
  municipality: 'City',
  municipalities: 'City',
  neighborhood: 'Neighborhood',
  neighborhoods: 'Neighborhood',

  // European Eurostat NUTS
  eurostatnuts1: 'EurostatNUTS1',
  eurostat_nuts_1: 'EurostatNUTS1',
  nuts1: 'EurostatNUTS1',
  nuts_1: 'EurostatNUTS1',
  eurostatnuts2: 'EurostatNUTS2',
  eurostat_nuts_2: 'EurostatNUTS2',
  nuts2: 'EurostatNUTS2',
  nuts_2: 'EurostatNUTS2',
  eurostatnuts3: 'EurostatNUTS3',
  eurostat_nuts_3: 'EurostatNUTS3',
  nuts3: 'EurostatNUTS3',
  nuts_3: 'EurostatNUTS3',

  // US Census & Metro Areas
  censustract: 'CensusTract',
  census_tract: 'CensusTract',
  'census tract': 'CensusTract',
  tract: 'CensusTract',
  tracts: 'CensusTract',
  censusblockgroup: 'CensusBlockGroup',
  blockgroup: 'CensusBlockGroup',
  censuszipcodetabulationarea: 'CensusZipCodeTabulationArea',
  zip: 'CensusZipCodeTabulationArea',
  zipcode: 'CensusZipCodeTabulationArea',
  zip_code: 'CensusZipCodeTabulationArea',
  'zip code': 'CensusZipCodeTabulationArea',
  censusregion: 'CensusRegion',
  censusdivision: 'CensusDivision',
  congressionaldistrict: 'CongressionalDistrict',
  censuscorebasedstatisticalarea: 'CensusCoreBasedStatisticalArea',
  cbsa: 'CensusCoreBasedStatisticalArea',
  usmetropolitandivision: 'USMetropolitanDivision',
  metroarea: 'USMetropolitanDivision',
  commutingzone: 'CommutingZone',

  // Schools & Education
  school: 'School',
  schools: 'School',
  publicschool: 'PublicSchool',
  privateschool: 'PrivateSchool',
  elementaryschool: 'ElementarySchool',
  highschool: 'HighSchool',
  middleschool: 'MiddleSchool',
  secondaryschool: 'SecondarySchool',
  schooldistrict: 'SchoolDistrict',
  collegeoruniversity: 'CollegeOrUniversity',
  university: 'CollegeOrUniversity',
  universities: 'CollegeOrUniversity',

  // Environmental & Infrastructure Facilities
  powerplant: 'PowerPlant',
  powerplants: 'PowerPlant',
  airqualitysite: 'AirQualitySite',
  waterqualitysite: 'WaterQualitySite',
  superfundsite: 'SuperfundSite',
  epareportingfacility: 'EpaReportingFacility',
  ipccplace_50: 'IPCCPlace_50',
  geogridplace_1deg: 'GeoGridPlace_1Deg',
  geogridplace_0_25deg: 'GeoGridPlace_0.25Deg',
  geogridplace_4km: 'GeoGridPlace_4KM',
};

/**
 * Normalizes an arbitrary place type string to a valid Data Commons schema type (PascalCase).
 * Resolves aliases and plural variations, falling back to PascalCase capitalization.
 */
export const normalizePlaceType = (type?: string): string => {
  if (!type?.trim()) return 'Country';

  const clean = type.trim().toLowerCase();
  if (PLACE_TYPE_MAP[clean]) {
    return PLACE_TYPE_MAP[clean];
  }

  // Fallback: convert snake_case / kebab-case / space-separated to PascalCase
  return clean
    .split(/[-_\s]+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join('');
};
