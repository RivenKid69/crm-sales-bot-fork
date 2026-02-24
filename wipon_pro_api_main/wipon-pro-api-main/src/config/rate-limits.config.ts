require('dotenv').config();

const getKeyValueFromStringAsInteger = (str: string) => {
  const result = {};
  const elements = str.split(';');
  elements.forEach((element) => {
    if (element.includes('=')) {
      const keyValue = element.split('=', 2);
      result[keyValue[0]] = keyValue[1];
    }
  });
  return result;
};

export default {
  user: {
    counter_key_prefix: 'user_rate_counter-',
    exceeding_flag_prefix: 'exceeding_flag-',
    limit: process.env.USER_RATE_LIMIT || 10000,
  },
  third_party: {
    cache_key_prefix: 'third_party-',
    global: process.env.THIRD_PARTY_GLOBAL_RATE_LIMIT || 500,
    locals: getKeyValueFromStringAsInteger(process.env.THIRD_PARTY_RATE_LIMITS || ''),
  },
};
