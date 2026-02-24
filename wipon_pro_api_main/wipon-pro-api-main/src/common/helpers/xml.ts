import { XMLBuilder } from 'fast-xml-parser';

const xmlBuilder = new XMLBuilder({ ignoreAttributes: false });
// Types для XML Builder неправильный. У xmlBuilder есть метод, build
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
export const buildXml = (o: any) => xmlBuilder.build(o);

export const array2xml = (array: Array<any>, xml = false, headerAttribute = [], isUtf = true) => {};

// public function array2xml($array, $xml = false, $headerAttribute = [], $utf8 = true)
// {
//   if (! $this->isType(gettype($array))) {
//   throw new XmlException('It is not possible to convert the data');
// }
//
//   if (! is_array($array)) {
//     $array = $array->toArray();
//   }
//
//   if ($xml === false) {
//     $xml = new \SimpleXMLElement($utf8 ? $this->template : config("xml.windows_template"));
//   }
//
//   $this->addAttribute($headerAttribute, $xml);
//
//   foreach ($array as $key => $value) {
//   if (is_array($value)) {
//     if (is_numeric($key)) {
//       $this->array2xml($value, $xml->addChild($this->caseSensitive('row_' . $key)));
//     } else {
//       $this->array2xml($value, $xml->addChild($this->caseSensitive($key)));
//     }
//   } else {
//     $xml->addChild($this->caseSensitive($key), htmlspecialchars($value));
//   }
// }
//
//   if ($utf8) {
//     return $xml->asXML();
//   } else {
//     return mb_convert_encoding($xml->asXML(), "windows-1251");
//   } // if utf8
// }
