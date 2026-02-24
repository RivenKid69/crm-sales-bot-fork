import { Injectable } from '@nestjs/common';
import { UserDao } from '../../common/dao/user.dao';
import { GenerateInvoiceDto } from './dto/generate-invoice.dto';
import { Response } from 'express';
import * as path from 'path';
import * as fs from 'fs';
// import * as html_to_pdf from 'html-pdf-node';
// import * as html_to_pdf from 'html-pdf';
// import * as ejs from 'ejs';
import { DESKTOP_TYPE, MOBILE_TYPE, subscriptionsTypePrice } from '../../config/subscription.config';

@Injectable()
export class PdfService {
  async generateInvoice(user: UserDao, generateInvoiceDto: GenerateInvoiceDto, response: Response) {
    return null;
    // const options = { format: 'A4' };
    // const pathToHtml = path.join(path.resolve(), 'dist', 'static', 'invoice', 'invoice.html');
    // const rawHtml = await fs.promises.readFile(pathToHtml, { encoding: 'utf-8' });
    //
    // const compiledHtml = ejs.compile(rawHtml, 'utf8');
    // const data = this.getInvoiceData(user, generateInvoiceDto);
    // const readyHtml = compiledHtml({
    //   data,
    // });
    //
    // // html_to_pdf.create(readyHtml, options).toBuffer((err, buffer) => {
    // //   if (err) throw new HttpException('Error in generating pdf invoice', 500);
    // //   response.set({ 'Content-Length': buffer.length });
    // //   response.end(buffer);
    // // });
    //
    // const file = { content: readyHtml };
    // html_to_pdf.generatePdf(file, options).then((pdfBuffer) => {
    //   response.set({ 'Content-Length': pdfBuffer.length });
    //   response.end(pdfBuffer);
    // });
  }

  getInvoiceData(user: UserDao, generateInvoiceDto: GenerateInvoiceDto) {
    const date = new Date();
    const formattedDigitDate = new Intl.DateTimeFormat('ru-RU', {
      year: '2-digit',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(date);

    const formattedReadableDate = new Intl.DateTimeFormat('ru-RU', {
      year: 'numeric',
      month: 'long',
      day: '2-digit',
    }).format(date);

    const rateName =
      generateInvoiceDto.type === MOBILE_TYPE
        ? 'Мобильное приложение'
        : generateInvoiceDto.type === DESKTOP_TYPE
        ? 'Компьютер'
        : 'ТСД';
    const ratePrice = subscriptionsTypePrice[generateInvoiceDto.type];
    const formattedRatePrice = this.priceFilter(ratePrice);

    let invoiceNumber = formattedDigitDate.replace(/[., :]/g, '');
    if (user.id) invoiceNumber += user.id;
    invoiceNumber += generateInvoiceDto.type;

    return {
      number: invoiceNumber,
      numberDate: formattedReadableDate,
      customerBin: generateInvoiceDto.bin,
      customerOrganization: generateInvoiceDto.organization,
      accountNumber: generateInvoiceDto.account_number,
      ratePrice: formattedRatePrice,
      rateName,
      rateLetterPrice: this.sum_letters(ratePrice),
    };
  }

  numLetters(k, d) {
    let i = '';
    const e = [
      [
        '',
        'тысяч',
        'миллион',
        'миллиард',
        'триллион',
        'квадриллион',
        'квинтиллион',
        'секстиллион',
        'септиллион',
        'октиллион',
        'нониллион',
        'дециллион',
      ],
      ['а', 'и', ''],
      ['', 'а', 'ов'],
    ];
    if (k == '' || k == '0') return ' ноль'; // 0
    k = k.split(/(?=(?:\d{3})+$)/); // разбить число в массив с трёхзначными числами
    if (k[0].length == 1) k[0] = '00' + k[0];
    if (k[0].length == 2) k[0] = '0' + k[0];
    for (let j = k.length - 1; j >= 0; j--) {
      if (k[j] != '000') {
        i =
          (((d && j == k.length - 1) || j == k.length - 2) && (k[j][2] == '1' || k[j][2] == '2')
            ? t(k[j], 1)
            : // eslint-disable-next-line @typescript-eslint/ban-ts-comment
              // @ts-ignore
              t(k[j])) +
          this.declOfNum(k[j], e[0][k.length - 1 - j], j == k.length - 2 ? e[1] : e[2]) +
          i;
      }
    }
    function t(k, d) {
      // преобразовать трёхзначные числа
      const e = [
        ['', ' один', ' два', ' три', ' четыре', ' пять', ' шесть', ' семь', ' восемь', ' девять'],
        [
          ' десять',
          ' одиннадцать',
          ' двенадцать',
          ' тринадцать',
          ' четырнадцать',
          ' пятнадцать',
          ' шестнадцать',
          ' семнадцать',
          ' восемнадцать',
          ' девятнадцать',
        ],
        [
          '',
          '',
          ' двадцать',
          ' тридцать',
          ' сорок',
          ' пятьдесят',
          ' шестьдесят',
          ' семьдесят',
          ' восемьдесят',
          ' девяносто',
        ],
        [
          '',
          ' сто',
          ' двести',
          ' триста',
          ' четыреста',
          ' пятьсот',
          ' шестьсот',
          ' семьсот',
          ' восемьсот',
          ' девятьсот',
        ],
        ['', ' одна', ' две'],
      ];
      return e[3][k[0]] + (k[1] == 1 ? e[1][k[2]] : e[2][k[1]] + (d ? e[4][k[2]] : e[0][k[2]]));
    }
    return i;
  }

  razUp(e) {
    return e[1].toUpperCase() + e.substring(2);
  }

  sum_letters(num) {
    num = num.toString();
    return this.razUp(this.numLetters(num, 1));
  }

  declOfNum(n, t, o) {
    // склонение именительных рядом с числительным: число (typeof = string), корень (не пустой), окончание
    const k = [2, 0, 1, 1, 1, 2, 2, 2, 2, 2];
    return t == '' ? '' : ' ' + t + (n[n.length - 2] == '1' ? o[2] : o[k[n[n.length - 1]]]);
  }

  priceFilter(value: number) {
    return Intl.NumberFormat('ru-RU', { style: 'decimal' }).format(value);
  }
}
