import {
  BaseEntity,
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  OneToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { LedgerDao } from './ledger.dao';

@Entity('invoices')
export class InvoiceDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'ledger_id' })
  ledger_id: number;

  @Column({ type: 'varchar', length: 200, name: 'bill_id' })
  bill_id: string;

  @Column({ type: 'varchar', length: 20 })
  provider: string;

  @Column({ type: 'varchar', length: 15 })
  status: string;

  @Column({ type: 'numeric', precision: 8, scale: 2 })
  amount: number;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @Column({ name: 'operation_id' })
  operation_id: string;

  @Column()
  session: string;

  @OneToOne(() => LedgerDao, (ledger) => ledger.invoice)
  @JoinColumn({ name: 'ledger_id' })
  ledger: LedgerDao;
}
